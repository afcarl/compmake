import sys
from compmake.utils.visualization import colored
from StringIO import StringIO


class StreamCapture:
    def __init__(self, transform=None, dest=None):
        ''' dest has write() and flush() '''
        self.buffer = StringIO()
        self.dest = dest
        self.transform = transform
        
    def write(self, s):
        self.buffer.write(s)
        if self.dest:
            if s.find('\n') != (len(s) - 1):
                lines = s.split('\n')
                for line in lines:
                    # XXX I'm not sure why we get empty lines here
                    if line:
                        if self.transform:
                            line = self.transform(line)
                        self.dest.write(line)
                        self.dest.write('\n')
            else:
                if self.transform:
                    s = self.transform(s)       
                self.dest.write(s)
                self.dest.write('\n')
            self.dest.flush()
        
    def flush(self):
        pass

class OutputCapture:
    
    def __init__(self, prefix, echo_stdout=True, echo_stderr=True):
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        t = lambda s: '%s| %s' % (prefix, colored(s, 'cyan', attrs=['dark']))
        dest = {True: sys.stdout, False: None}[echo_stdout]     
        self.stdout_replacement = StreamCapture(transform=t, dest=dest)
        sys.stdout = self.stdout_replacement
        
        t = lambda s: '%s| %s' % (prefix, colored(s, 'red', attrs=['dark']))
        dest = {True: sys.stderr, False: None}[echo_stderr]      
        self.stderr_replacement = StreamCapture(transform=t, dest=dest)
        sys.stderr = self.stderr_replacement
        
    def deactivate(self):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
        
