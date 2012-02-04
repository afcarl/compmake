from . import Event, compmake_registered_events
from ..structures import CompmakeException
from ..utils import error, wildcard_to_regexp
import traceback


class EventHandlers:
    # event name -> list of functions
    handlers = {}
    # list of handler, called when there is no other specialized handler
    fallback = []


def remove_all_handlers():
    ''' Removes all event handlers. Useful when
        events must not be processed locally but routed
        to the original process. '''
    EventHandlers.handlers = {}
    EventHandlers.fallback = []


def register_fallback_handler(handler):
    '''
        Registers an handler who is going to be called when no other handler
        can deal with an event. Useful to see if we are ignoring some event.
    '''
    EventHandlers.fallback.append(handler)


# TODO: make decorator
def register_handler(event_name, handler):
    ''' Registers an handler with an event name.
    The event name might contain asterisks. "*" matches 
    all. '''

    if event_name.find('*') > -1:
        regexp = wildcard_to_regexp(event_name)

        for event in compmake_registered_events.keys():
            if regexp.match(event):
                register_handler(event, handler)

    else:
        if not event_name in EventHandlers.handlers:
            EventHandlers.handlers[event_name] = []
        EventHandlers.handlers[event_name].append(handler)


def publish(event_name, **kwargs):
    if not event_name in compmake_registered_events:
        raise CompmakeException('Event %r not registered' % event_name)
    spec = compmake_registered_events[event_name]
    for key in kwargs.keys():
        if not key in spec.attrs:
            msg = ('Passed attribute %r for event type %r but only found '
                   'attributes %s.' % (key, event_name, spec.attrs))
            raise CompmakeException(msg)
    event = Event(event_name, **kwargs)
    broadcast_event(event)


def broadcast_event(event):
    handlers = EventHandlers.handlers.get(event.name, None)
    if handlers:
        for handler in handlers:
            try:
                handler(event)
                # TODO: do not catch interrupted, etc.
            except Exception as e:
                e = traceback.format_exc(e)
                msg = 'compmake BUG: Error in handler %s:\n%s\n' % (handler, e)
                error(msg)
    else:
        for handler in EventHandlers.fallback:
            handler(event)

