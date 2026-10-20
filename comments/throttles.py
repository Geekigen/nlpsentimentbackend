from rest_framework.throttling import SimpleRateThrottle


class CommentCreateThrottle(SimpleRateThrottle):
    """Two new comments per client IP each minute. Reads and analysis are not limited."""

    scope = "comment_create"
    rate = "2/min"

    def allow_request(self, request, view):
        if getattr(view, "action", None) != "create":
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class AskThrottle(SimpleRateThrottle):
    """Six Ask AI questions per client IP each minute."""

    scope = "ask"
    rate = "6/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
