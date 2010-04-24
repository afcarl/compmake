from time import time

from compmake.structures import Computation, Cache, ParsimException

from compmake.stats import progress, progress_string, \
    print_progress, progress_reset_cache

from compmake.process_storage import get_job_cache, set_job_cache, \
    delete_job_cache, \
    get_job_userobject, is_job_userobject_available, delete_job_userobject, \
    set_job_userobject, get_job_tmpobject, is_job_tmpobject_available, \
    set_job_tmpobject, delete_job_tmpobject

def clean_target(job_id):
    # Cleans associated objects
    mark_remake(job_id)
    # Removes also the Cache object 
    delete_job_cache(job_id)
    
def mark_more(job_id):
    cache = get_job_cache(job_id)
    cache.state = Cache.MORE_REQUESTED
    set_job_cache(job_id, cache)

def mark_remake(job_id):
    if is_job_userobject_available(job_id):
        delete_job_userobject(job_id)
    if is_job_tmpobject_available(job_id):
        delete_job_tmpobject(job_id)
        
    cache = get_job_cache(job_id)
    cache.state = Cache.NOT_STARTED
    set_job_cache(job_id, cache)

up_to_date_cache = set()
def up_to_date(job_id):
    global up_to_date_cache
    if job_id in up_to_date_cache:
        return True, '(cached)'
    
    """ Check that the job is up to date. 
    We are up to date if:
    *) we are in the up_to_date_cache
       (nothing uptodate can become not uptodate so this is generally safe)
    OR
    1) we have a cache AND the timestamp is not 0 (force remake) or -1 (temp)
      AND finished = True
    2) the children are up to date AND
    3) the children timestamp is older than this timestamp AND
    
    Returns:
    
        boolean, explanation 
    
    """ 
    
    cache = get_job_cache(job_id) # OK
    
    if cache.state == Cache.NOT_STARTED:
        return False, 'Not started'
        
    computation = Computation.id2computations[job_id]
    for child in computation.depends:
        if not up_to_date(child.job_id):
            return False, 'Children not up to date.'
        else:
            this_timestamp = cache.timestamp
            child_timestamp = get_job_cache(child.job_id).timestamp
            if child_timestamp > this_timestamp:
                return False, 'Children have been updated.'
    
    # FIXME BUG if I start (in progress), children get updated,
    # I still finish the computation instead of starting again
    if cache.state ==  Cache.IN_PROGRESS:
        return False, 'Resuming progress'
    elif cache.state ==  Cache.FAILED:
        return False, 'Failed'
            
    assert( cache.state in [Cache.DONE, Cache.MORE_REQUESTED] )

    up_to_date_cache.add(job_id)
    
    return True, ''
    
    
from types import GeneratorType


def make(job_id, more=False):
    """ Returns the user-object """
    up, reason = up_to_date(job_id)
    cache = get_job_cache(job_id)
    want_more = cache.state == Cache.MORE_REQUESTED
    if up and not (more and want_more):
        # print "%s is up to date" % job_id
        assert(is_job_userobject_available(job_id))
        return get_job_userobject(job_id)
    else:
        if up and (more and want_more): # XXX review the logic 
            reason = 'want more'
        print "Making %s (%s)" % (job_id, reason)
        computation = Computation.id2computations[job_id]
        deps = []
        for child in computation.depends:
            deps.append(make(child.job_id))
      
        assert(cache.state in [Cache.NOT_STARTED, Cache.IN_PROGRESS,
                               Cache.MORE_REQUESTED, Cache.DONE])
        
        if cache.state == Cache.NOT_STARTED:
            previous_user_object = None
            cache.state = Cache.IN_PROGRESS
        elif cache.state == Cache.IN_PROGRESS:
            if is_job_tmpobject_available(job_id):
                previous_user_object = get_job_tmpobject(job_id)
            else:
                previous_user_object = None
        elif cache.state == Cache.MORE_REQUESTED:
            assert(is_job_userobject_available(job_id))
            if is_job_tmpobject_available(job_id):
                # resuming more computation
                previous_user_object = get_job_tmpobject(job_id)
            else:
                # starting more computation
                previous_user_object = get_job_userobject(job_id)
        elif cache.state == Cache.DONE:
            # If we are done, it means children have been updated
            assert(not up)
            previous_user_object = None
        else:
            assert(False)
        
        # update state
        set_job_cache(job_id, cache)
        
        progress(job_id, 0, None)
        result = computation.compute(deps, previous_user_object)
        if type(result) == GeneratorType:
            try:
                while True:
                    next = result.next()
                    if isinstance(next, tuple):
                        if len(next) != 3:
                            raise ParsimException('If computation yields a tuple, ' +
                                                  'should be a tuple with 3 elemnts.'+
                                                  'Got: %s' % next)
                        user_object, num, total = next
                        progress(job_id, num, total)
                        set_job_tmpobject(job_id, user_object)
                        
            except StopIteration:
                pass
        else:
            progress(job_id, 1, 1)
            user_object = result
        
        set_job_userobject(job_id, user_object)
        delete_job_tmpobject(job_id)
        
        cache.state = Cache.DONE
        cache.timestamp = time()
        set_job_cache(job_id, cache)
        
        return user_object
        
def top_targets():
    """ Returns a list of all jobs which are not needed by anybody """
    return [x.job_id for x in Computation.id2computations.values() if len(x.needed_by) == 0]
    
def bottom_targets():
    """ Returns a list of all jobs with no dependencies """
    return [x.job_id for x in Computation.id2computations.values() if len(x.depends) == 0]


from multiprocessing import Pool, TimeoutError, cpu_count
from time import sleep
import sys

def dependencies_up_to_date(job_id):
    computation = Computation.id2computations[job_id]
    dependencies_up_to_date = True
    for child in computation.depends:
        child_up, reason = up_to_date(child.job_id) 
        if not child_up:
            return False
    return True

def list_targets(jobs):
    """ returns two sets:
         todo:  set of job ids to do
         ready_todo: subset of jobs that are ready to do """
    todo = []
    ready_todo = []
    for job_id in jobs:
        up, reason = up_to_date(job_id)
        if not up:
            todo.append(job_id)
            computation = Computation.id2computations[job_id]
            dependencies_up_to_date = True
            for child in computation.depends:
                child_up, reason = up_to_date(child.job_id) 
                if not child_up:
                      dependencies_up_to_date = False
                      its_todo, its_ready_todo = list_targets([child.job_id])
                      todo.extend(its_todo)
                      ready_todo.extend(its_ready_todo)
            if dependencies_up_to_date:
                ready_todo.append(job_id)
        else:
            pass
            # print "Job %s uptodate" % job_id
    return set(todo), set(ready_todo)
    
def make_targets(targets, more=False):
    # todo: jobs which we need to do, eventually
    # ready_todo: jobs which are ready to do (dependencies satisfied)
    todo, ready_todo = list_targets(targets)    
    # jobs currently in processing
    processing = set()
    # jobs which have failed
    failed = set()
    # jobs completed succesfully
    done = set()

    def write_status():
        sys.stderr.write(
         ("compmake: done %4d | failed %4d | todo %4d "+
         "| ready %4d | processing %4d \n") % (
                len(done), len(failed), len(todo),
                len(ready_todo), len(processing) ))

    # Until we have something to do
    while todo:
        # single thread, we do one thing at a time
        assert(not processing)
        # Unless there are circular references,
        # something should always be ready to do
        assert(ready_todo)
        
        
        # todo: add task priority
        job_id = ready_todo.pop()
        
        processing.add(job_id)
        
        write_status()
        
        try:
            do_more = more and job_id in targets
            # try to do the job
            make(job_id, more=do_more)
            # if we succeed, mark as done
            done.add(job_id)
            # now look for its parents
            parent_jobs = [x.job_id for x in \
                           Computation.id2computations[job_id].needed_by ]
            for opportunity in todo.intersection(set(parent_jobs)):
                # opportunity is a parent that we should do
                # if its dependencies are satisfied, we can put it 
                #  in the ready_todo list
                if dependencies_up_to_date(opportunity):
                    # print "Now I can make %s" % opportunity
                    ready_todo.add(opportunity)
            
        except Exception as e:
            # if we fail
            print "Job %s failed: %s" % (name, e)
            failed.add(job_id)
            computation = Computation.id2computations[job_id]
            # TODO: mark dependencies as failed
            if len(computation.needed_by) > 0: 
                print "Exiting because job %s is needed" % job_id
                sys.exit(-1) # XXX
        finally:
            # in any case, we remove the job from the todo list
            todo.remove(job_id)
            processing.remove(job_id)
        
    write_status()
 

def parmake_targets(targets, more=False, processes=None):
    # See make_targets for comments on the common structure
    pool = Pool(processes=processes)
    max_num_processing = cpu_count() + 1
    
    todo, ready_todo = list_targets(targets)    
    processing = set()
    # this hash contains  job_id -> async result
    processing2result = {}
    failed = set()
    done = set()

    def write_status():
        sys.stderr.write(
         ("parmake: done %4d | failed %4d | todo %4d "+
         "| ready %4d | processing %4d \n") % (
                len(done), len(failed), len(todo),
                len(ready_todo), len(processing) ))

    while todo:
        # note that in the single-thread processing=[]
        assert(ready_todo or processing) 
        assert(not failed.intersection(todo))

        # add jobs up to saturations
        while ready_todo and len(processing) <= max_num_processing:
            # todo: add task priority
            job_id = ready_todo.pop()
            assert(job_id in todo)
            processing.add(job_id)
            make_more_of_this = more and (job_id in targets)
            processing2result[job_id] = \
                pool.apply_async(parmake_job, [job_id, make_more_of_this])
   
        write_status()
        
        # Loop until we get some response
        while True:
            received_some_results = False
            for job_id, async_result in processing2result.items():
                assert(job_id in processing)
                assert(job_id in todo)
                assert(not job_id in ready_todo)
                try:
                    async_result.get(timeout=0.01)
                    del processing2result[job_id]
                    
                    received_some_results = True
                    done.add(job_id)
                    todo.remove(job_id)
                    processing.remove(job_id)
                    
                    parent_jobs = [x.job_id for x in \
                           Computation.id2computations[job_id].needed_by ]
                    for opportunity in todo.intersection(set(parent_jobs)):
                        if dependencies_up_to_date(opportunity):
                            # print "Now I can make %s" % opportunity
                            ready_todo.add(opportunity)
                        
                except TimeoutError:
                    # it simply means the job is not ready
                    pass
                except Exception as e:
                    print "Job %s failed: %s" % (job_id, e)
                    failed.add(job_id)
                    todo.remove(job_id)
                    processing.remove(job_id)
                    del processing2result[job_id]
    
                    computation = Computation.id2computations[job_id]
                    if len(computation.needed_by) > 0: 
                        print "Exiting because job %s is needed" % job_id
                        sys.exit(-1)
            if received_some_results:
                break
        write_status()
    write_status()
    
def parmake_job(job_id, more=False):
    import compmake
    compmake.storage.redis = None
    #progress_set_queue(queue)
    try:
        make(job_id, more)
    except Exception as e:
        print "**Job %s failed: %s" % ( job_id, e)
        raise e
    

#def parmake(targets=None, more=False, processes=None):
#    pool = Pool(processes=processes)
#        
#    """ If no target is passed, we do all top_targets """
#    if targets is None:
#        targets = top_targets() 
#        
#    # jobs currently in processing
#    processing = set()
#    failed = set()
#    done = set()
#    processing2result = {}
#    # print "Targets %d " % len(targets)
#    while True:
#        progress_reset_cache(processing)
#        
#        for name, result in processing2result.items():
#            try:
#                result.get(timeout=0.1)
#                done.add(name)
#                processing.remove(name)
#                del processing2result[name]
#            except TimeoutError:
#                pass
#            except Exception as e:
#                print "Job %s failed: %s" % (name, e)
#                failed.add(name)
#                processing.remove(name)
#                del processing2result[name]
#
#                computation = Computation.id2computations[name]
#                if len(computation.needed_by) > 0: 
#                    print "Exiting because job %s is needed" % name
#                    sys.exit(-1)
#        
#        todo, ready_todo = list_targets(targets)
#        
#        todo = set(todo).difference(failed)
#        
#        if len(todo) == 0:
#            break
#        
#        ready_not_processing = set(ready_todo).difference(processing, failed) 
#
#        sys.stderr.flush()
#        
#        for job_id in ready_not_processing:
#            #print "Launching %s " % job_id
#            processing.add(job_id)
#            make_more_of_this = more and (job_id in targets)
#            processing2result[job_id] = \
#                pool.apply_async(parmake_job, [job_id, make_more_of_this])
#        
#        sys.stderr.write("--\nDone %d Failed %d Todo %d, Processing %d new %d\nStats %s--" % (
#                        len(done), len(failed), len(todo), 
#                                              len(processing), 
#                                              len(ready_not_processing), 
#                                              progress_string()))
#        sleep(1)



def make_sure_cache_is_sane():
    return
# XXX review this
    """ Checks that the cache is sane, deletes things that cannot be open """
    for job_id in Computation.id2computations.keys():
        if is_cache_available(job_id):
            try:
                get_cache(job_id)
               # print "%s sane" % job_id
            except:
                print "Cache %s not sane. Deleting." % job_id
                delete_cache(job_id)


