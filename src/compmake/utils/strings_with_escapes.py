import re
from . import get_screen_columns


def remove_escapes(s):
    escape = re.compile('\x1b\[..?m')
    return escape.sub("", s)


def get_length_on_screen(s):
    """ Returns the length of s without the escapes """
    return len(remove_escapes(s))

debug_padding = False


def pad_to_screen(s, pad=" ", last=None):
    ''' 
        Pads a string to the terminal size.
    
        The string length is computed after removing shell 
        escape sequences. 
    '''

    total_screen_length = get_screen_columns()

    if debug_padding:
        return pad_to_screen_length(s, total_screen_length, pad="-", last='|')
    else:
        return pad_to_screen_length(s, total_screen_length, pad=pad, last=last)


def pad_to_screen_length(s, desired_screen_length, pad=" ", last=None,
                         align_right=False):
    ''' 
        Pads a string so that it will appear of the given size 
        on the terminal.
        
        align_right: aligns right instead of left (default) 
    '''
    assert isinstance(desired_screen_length, int)
    # todo: assert pad = 1
    current_size = get_length_on_screen(s)

    if last is None:
        last = pad

    if current_size < desired_screen_length:
        nadd = (desired_screen_length - current_size)
        padding = (pad * (nadd - 1))
        if align_right:
            s = last + padding + s
        else:
            s = s + padding + last

    return s