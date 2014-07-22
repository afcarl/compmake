from optparse import OptionParser
import os
import sys
import traceback

from contracts import contract
import contracts

import compmake

from .. import (version, set_compmake_status,
    CompmakeConstants, logger)
from ..config import config_populate_optparser
from ..context import Context
from ..jobs import all_jobs, set_namespace
from ..state import set_inside_compmake_script
from ..storage import StorageFilesystem
from ..structures import UserError
from ..ui import (error, interactive_console, batch_command,
    interpret_commands_wrap, info)
from ..utils import setproctitle
from .scripts_utils import wrap_script_entry_point


# TODO: revise all of this
@contract(context=Context)
def read_rc_files(context):
    assert context is not None
    possible = ['compmake.rc', '~/.compmake/compmake.rc']
    done = False
    for x in possible:
        x = os.path.expanduser(x)
        if os.path.exists(x):
            read_commands_from_file(filename=x, context=context)
            done = True
    if not done:
        # logger.info('No configuration found (looked for %s)' % "; ".join(possible))
        pass
            
@contract(context=Context, filename=str)
def read_commands_from_file(filename, context):
    assert context is not None
    logger.info('Reading configuration from %r' % filename)
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if line[0] == '#':
                continue
            interpret_commands_wrap(line, context)

usage = """
The "compmake" script takes a DB directory as argument:

    $ compmake  <compmake_storage>  [-c COMMAND]
    
For example: 

    $ compmake out-compmake -c "clean; parmake n=2"
   
"""

# 
# 
# usage = """
# The "compmake" script has takes either a module name or a DB directory.
# 
# 1) In the basic usage, pass a module name, and an optional command with "-c".
# 
#     $ compmake  <module_name>  [-c COMMAND]
#     
#    For example, if you have a file "example.py", you could run
#    
#     $ compmake example
#     
#    or 
#     
#     $ compmake example -c "clean; parmake n=2"
# 
# 
# 2) Advanced usage: load jobs from an existing directory.
# 
#    $ compmake compmake_storage
#    
#    
# """

def main():
    wrap_script_entry_point(compmake_main,
                            exceptions_no_traceback=(UserError,))

def compmake_main(args):
    if not '' in sys.path:
        sys.path.append('')
        
    set_inside_compmake_script()

    setproctitle('compmake')

    parser = OptionParser(version=version, usage=usage)

    parser.add_option("--profile", default=False, action='store_true',
                      help="Use Python profiler")

    parser.add_option("--contracts", default=False, action='store_true',
                      help="Activate PyContracts")

    parser.add_option("-c", "--command",
                      default=None,
                      help="Run the given command")
    
    parser.add_option('-n', '--namespace',
                      default='default')

    parser.add_option('--retcodefile',
                      help='If given, the return value is written in this file. '
                           'Useful to check when compmake finished in a grid environment. ',
                      default=None)

    parser.add_option('--nosysexit',  default=False, action='store_true',
                      help='Does not sys.exit(ret); useful for debugging.')
                    

    config_populate_optparser(parser)

    (options, args) = parser.parse_args(args)

    if not options.contracts:
        info('Disabling PyContracts; use --contracts to activate.')
        contracts.disable_all()

    # We load plugins after we parsed the configuration
    from compmake import plugins  # @UnusedImport

#    if options.redis_events:
#        if not compmake_config.db == 'redis':
#            error('Cannot use redis_events without redis.')
#            sys.exit(-2)
#
#        from compmake.storage.redisdb import RedisInterface
#
#        # register an handler that will capture all events    
#        def handler(event):
#            RedisInterface.events_push(event)
#
#        remove_all_handlers()
#        register_handler("*", handler)

    set_namespace(options.namespace)
    
    # XXX make sure this is the default
    if not args:
        msg = ('I expect at least one argument (db path).'
               ' Use "compmake -h" for usage information.')
        raise UserError(msg)

    if len(args) >= 2:
        msg = 'I only expect one argument. Use "compmake -h" for usage information.'
        msg += '\n args: %s' % args
        raise UserError(msg)

    # if the argument looks like a dirname
    one_arg = args[0]     
    if os.path.exists(one_arg) and os.path.isdir(one_arg):
        loaded_db = True
        # If there is a compmake/ folder inside, take it as the root
        child = os.path.join(one_arg, 'compmake')
        if os.path.exists(child):
            one_arg = child

        context = load_existing_db(one_arg)
        # If the context was custom we load it
        if 'context' in context.compmake_db:
            context = context.compmake_db['context']
    else:
        msg = 'Directory not found: %s' % one_arg
        raise UserError(msg)
#         check_not_filename(one_arg)
# 
#         dirname = get_compmake_config('path')
#         db = StorageFilesystem(dirname)
#         context = Context(db=db)
#         Context._default = context
#         load_module(one_arg)

    args = args[1:]
 
    def go(context):
        assert context is not None

        if options.command:
            set_compmake_status(CompmakeConstants.compmake_status_slave)
        else:    
            set_compmake_status(CompmakeConstants.compmake_status_interactive)
            
        read_rc_files(context)
        
        if options.command:
            retcode = batch_command(options.command, context=context)
        else:
            retcode = interactive_console(context=context)
            
        if options.retcodefile is not None:
            if isinstance(retcode, str):
                retcode = 1
            write_atomic(options.retcodefile, str(retcode))
        
        if options.nosysexit:
            return retcode
        else:
            sys.exit(retcode)

    if not options.profile:
        return go(context)
    else:
        # XXX: change variables
        import cProfile
        cProfile.runctx('go(context)', globals(), locals(), 'out/compmake.profile')
        import pstats
        p = pstats.Stats('out/compmake.profile')
        n = 30
        p.sort_stats('cumulative').print_stats(n)
        p.sort_stats('time').print_stats(n)


def write_atomic(filename, contents):
    dirname = os.path.dirname(filename)
    if dirname:
        if not os.path.exists(dirname):
            try:
                os.makedirs(dirname)
            except:
                pass
    tmpFile = filename + '.tmp'
    f = open(tmpFile, 'w')
    f.write(contents)
    f.flush()
    os.fsync(f.fileno()) 
    f.close()
    os.rename(tmpFile, filename)


@contract(returns=Context)
def load_existing_db(dirname):
    assert os.path.isdir(dirname)
    logger.info('Loading existing jobs from DB directory %r' % dirname)
    
    # check if it is compressed
    files = os.listdir(dirname)
    one = files[0]
    if '.gz' in one:
        compress = True
    else:
        compress = False

    db = StorageFilesystem(dirname, compress=compress)
    context = Context(db=db)
    
    jobs = list(all_jobs(db=db))
    if not jobs:
        msg = 'No jobs found in that directory.'
        raise UserError(msg)
    logger.info('Found %d existing jobs.' % len(jobs))
    context.reset_jobs_defined_in_this_session(jobs)
    
    return context


def check_not_filename(module_name):
    if module_name.endswith('.py') or (module_name.find('/') > 0):
        msg = ('You passed a string %r which looks like a filename.' % 
                module_name)
        msg += ' However, I need a module name.'
        raise UserError(msg)


def load_module(module_name):
#    if module_name.endswith('.py') or (module_name.find('/') > 0):
#        warning('You passed a string %r which looks like a filename.' % 
#                module_name)
#        module_name = module_name.replace('/', '.')
#        module_name = module_name.replace('.py', '')
#        warning('However, I need a module name. I will try with %r.' % 
#                module_name)

    set_namespace(module_name)

    compmake.is_it_time = True
    try:
        info('Importing module %r' % module_name)
        __import__(module_name)
    except Exception as e:
        msg = ('Error while trying to import module "%s": %s' % 
              (module_name, e))
        msg += '\n path: %s' % sys.path
        error(msg)
        traceback.print_exc(file=sys.stderr)
        raise 
