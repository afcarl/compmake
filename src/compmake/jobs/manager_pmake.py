from .manager import AsyncResultInterface, Manager
from .manager_multiprocessing import parmake_job2
from Queue import Empty
from compmake.events.registrar import broadcast_event, publish
from compmake.jobs.manager_multiprocessing import Shared
from compmake.state import get_compmake_config
from compmake.structures import HostFailed, JobFailed
from contracts import contract
from contracts.utils import check_isinstance, indent
from multiprocessing import TimeoutError
from multiprocessing.queues import Queue
import multiprocessing
import os
import signal
import sys
import tempfile
import warnings
import traceback


def pmake_worker(name, job_queue, result_queue):
    f = open('pmake_worker-%s.log' % name, 'w')
    def log(s):
        f.write('%s: ' % name)
        f.write(s)
        f.write('\n')
        f.flush()
        
    log('started manual_function()')
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    try:
        while True:
            
            log('Listening for job')
            job = job_queue.get(block=True)
            log('got job: %s' % str(job))
            function, arguments = job
            
            try:
                result = function(arguments)
            except JobFailed as e:
                log('Job failed, putting notice.')
                result_queue.put(dict(fail=str(e)))
            else:
                log('result: %s' % str(result))
                log('job finished. Putting in queue...')
                result_queue.put(result, block=True)
                
            log('...done.')

        #except KeyboardInterrupt: pass
    except BaseException as e:
        msg = 'aborted because of uncaptured:\n' + indent( traceback.format_exc(e), '| ')
        log(msg)
        result_queue.put(dict(abort=msg))
    except:
        msg = 'aborted-unknown'
        log(msg)
        result_queue.put(dict(abort=msg))
        
    log('clean exit.')
        
class PmakeSub():
    def __init__(self, name):
        self.name = name
        
        self.job_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()

        self.proc = multiprocessing.Process(target=pmake_worker,
                                      args=(self.name, 
                                            self.job_queue, self.result_queue))
        self.proc.start()

    def apply_async(self, function, arguments):
        self.job_queue.put((function, arguments))
        return PmakeResult(self.result_queue, job=arguments)
 
 
class PmakeResult(AsyncResultInterface):
    """ Wrapper for the async result object obtained by pool.apply_async """
    
    def __init__(self, result_queue, job):
        self.result_queue = result_queue
        self.result = None
        self.job = job
    
        self.count = 0
    def ready(self):
        self.count += 1
        
        try: 
            self.result = self.result_queue.get(block=False)
        except Empty:
            #if self.count > 1000 and self.count % 100 == 0:
            #    print('ready()?  still waiting on %s' % str(self.job))
            return False
        else:
            return True    
        
    def get(self, timeout=0):  # @UnusedVariable
        if self.result is None:
            try:
                self.result = self.result_queue.get(block=True, timeout=timeout)
            except Empty as e:
                raise TimeoutError(e)
            
        check_isinstance(self.result, dict)
        if 'fail' in self.result:
            msg = 'Currently debuging exceptions so full trace not available.'
            msg += '\n' + indent(self.result['fail'], '| ')
            raise JobFailed(msg)
        
        if 'abort' in self.result:
            msg = 'Currently debuging exceptions so full trace not available.'
            msg += '\n' + indent(self.result['abort'], '| ')

            raise HostFailed(msg)
            
        return self.result


class PmakeManager(Manager):
    ''' Specialization of Manager for local multiprocessing, using
        an adhoc implementation of "pool" because of bugs of the 
        Python 2.7 implementation 
     '''

    def __init__(self, context, num_processes=None, recurse=False):
        Manager.__init__(self, context=context, recurse=recurse)
        self.num_processes = num_processes
        self.last_accepted = 0

         
    def process_init(self):
        if self.num_processes is None:
            self.num_processes = get_compmake_config('max_parallel_jobs')

        Shared.event_queue = Queue(self.num_processes * 1000)
        # info('Starting %d processes' % self.num_processes)
        
        self.sub_available = set()
        self.sub_processing = set() # available + processing = subs.keys
        self.subs = {} # name -> sub
        for i in range(self.num_processes):
            name = 'w%02d' % i
            self.subs[name] = PmakeSub(name) 
        
        self.job2subname = {}
        
        # all are available
        self.sub_available.update(self.subs)

        kwargs = {}

        if sys.hexversion >= 0x02070000:
            # added in 2.7.2
            kwargs['maxtasksperchild'] = 1

        self.max_num_processing = self.num_processes

    # XXX: boiler plate
    def get_resources_status(self):
        resource_available = {}
        
        # only one job at a time
        process_limit_ok = len(self.sub_processing) < self.max_num_processing
        if not process_limit_ok:
            resource_available['nproc'] = (False,
                'nproc %d >= %d' % (len(self.sub_processing), self.max_num_processing))
            # this is enough to continue
            return resource_available
        else:
            resource_available['nproc'] = (True, '')
                        
        return resource_available

    @contract(reasons_why_not=dict)
    def can_accept_job(self, reasons_why_not):
        resources = self.get_resources_status()
        some_missing = False
        for k, v in resources.items():
            if not v[0]:
                some_missing = True
                reasons_why_not[k] = v[1]
        if some_missing:
            return False
#         self.last_accepted = time.time()
        return True
     

    def instance_job(self, job_id):
        publish(self.context, 'worker-status', job_id=job_id, status='apply_async')
        handle, tmp_filename = tempfile.mkstemp(prefix='compmake', text=True)
        os.close(handle)
        os.remove(tmp_filename)
        assert len(self.sub_available) > 0
        name = sorted(self.sub_available)[0]
        self.sub_available.remove(name)
        assert not name in self.sub_processing
        self.sub_processing.add(name)
        sub = self.subs[name]
        
        self.job2subname[job_id] = name
        
        async_result = sub.apply_async(parmake_job2, (job_id, self.context, tmp_filename))
        return async_result

    def event_check(self):
        while True:
            try:
                event = Shared.event_queue.get(block=False)  # @UndefinedVariable
                event.kwargs['remote'] = True
                broadcast_event(self.context, event)
            except Empty:
                break

    def process_finished(self):
        for name, sub in self.subs.items():  # @UnusedVariable
            sub.proc.terminate()
        for name, sub in self.subs.items():  # @UnusedVariable
            sub.proc.join()
        
    def job_failed(self, job_id):
        Manager.job_failed(self, job_id)
        self._clear(job_id)
        
    def _clear(self, job_id):
        assert job_id in self.job2subname
        name = self.job2subname[job_id]
        del self.job2subname[job_id]
        assert name in self.sub_processing
        assert name not in self.sub_available
        self.sub_processing.remove(name)
        self.sub_available.add(name)
        
    def job_succeeded(self, job_id):
        Manager.job_succeeded(self, job_id)
        self._clear(job_id)

    def cleanup(self):
        warnings.warn('to do')
        self.process_finished()
        
 