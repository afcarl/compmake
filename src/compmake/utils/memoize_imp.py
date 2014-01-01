from decorator import decorator
from .frozen import frozendict2


__all__ = ['memoize_simple']


def memoize_simple(obj):
    cache = obj.cache = {}

    def memoizer(f, *args, **kwargs):
        key = (args, frozendict2(kwargs))
        if key not in cache:
            cache[key] = f(*args, **kwargs)
            # print('memoize: %s %d storage' % (obj, len(cache)))
        return cache[key]
    
    return decorator(memoizer, obj)