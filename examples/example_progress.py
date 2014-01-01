#!/usr/bin/env python

from compmake import comp, progress, compmake_console
import time


def mylongfunction():
    directories = ['a', 'b', 'c', 'd', 'e']
    n = len(directories)

    for i, d in enumerate(directories):
        progress('Processing directories (first)', (i, n), 'Directory %s' % d)
        
        N = 3
        for k in range(N):
            progress('Processing files (a)', (k, N), 'file #%d' % k)
            
            time.sleep(1)
            
    for i, d in enumerate(directories):
        progress('Processing directories (second)', (i, n), 'Directory %s' % d)
    
        N = 3
        for k in range(N):
            progress('Processing files (b)', (k, N), 'file #%d' % k)
            
            time.sleep(1)
            
           
comp(mylongfunction)

print('This is an example of how to use the "progress" function.')
compmake_console()