from threading import Thread, Event
from Queue import Queue, Empty

from spec import Spec, skip, eq_, raises

from invoke import Responder, FailingResponder, ResponseFailure


# NOTE: StreamWatcher is basically just an interface/protocol; no behavior to
# test of its own. So this file tests Responder primarily, and some subclasses.

class Responder_(Spec):
    def keeps_track_of_seen_index_per_thread(self):
        # Instantiate a single object which will be used in >1 thread
        r = Responder(pattern='foo', response='bar fight') # meh
        # Thread body func allowing us to mimic actual IO thread behavior, with
        # Queues used in place of actual pipes/files
        def body(responder, in_q, out_q, finished):
            while not finished.is_set():
                try:
                    # NOTE: use nowait() so our loop is hot & can shutdown ASAP
                    # if finished gets set.
                    stream = in_q.get_nowait()
                    for response in r.submit(stream):
                        out_q.put_nowait(response)
                except Empty:
                    pass
        # Create two threads from that body func, and queues/etc for each
        t1_in, t1_out, t1_finished = Queue(), Queue(), Event()
        t2_in, t2_out, t2_finished = Queue(), Queue(), Event()
        t1 = Thread(target=body, args=(r, t1_in, t1_out, t1_finished))
        t2 = Thread(target=body, args=(r, t2_in, t2_out, t2_finished))
        # Start the threads
        t1.start()
        t2.start()
        try:
            stream = 'foo fighters'
            # First thread will basically always work
            t1_in.put(stream)
            eq_(t1_out.get(), 'bar fight')
            # Second thread get() will block/timeout if threadlocals aren't in
            # use, because the 2nd thread's copy of the responder will not have
            # its own index & will thus already be 'past' the `foo` in the
            # stream.
            t2_in.put(stream)
            eq_(t2_out.get(timeout=1), 'bar fight')
        except Empty:
            assert False, "Unable to read from thread 2 - implies threadlocal indices are broken!" # noqa
        # Close up.
        finally:
            t1_finished.set()
            t2_finished.set()
            t1.join()
            t2.join()

    def yields_response_when_regular_string_pattern_seen(self):
        r = Responder(pattern='empty', response='handed')
        eq_(list(r.submit('the house was empty')), ['handed'])

    def yields_response_when_regex_seen(self):
        r = Responder(pattern=r'tech.*debt', response='pay it down')
        eq_(list(r.submit("technically, it's still debt")), ['pay it down'])

    def multiple_hits_within_stream_yield_multiple_responses(self):
        r = Responder(pattern='jump', response='how high?')
        eq_(list(r.submit('jump, wait, jump, wait')), ['how high?'] * 2)

    def patterns_span_multiple_lines(self):
        r = Responder(pattern=r'call.*problem', response='So sorry')
        output = """
You only call me
when you have a problem
You never call me
Just to say hi
"""
        eq_(list(r.submit(output)), ['So sorry'])


class FailingResponder_(Spec):
    def behaves_like_regular_responder_by_default(self):
        r = FailingResponder(
            pattern='ju[^ ]{2}',
            response='how high?',
            failure_sentinel='lolnope',
        )
        eq_(list(r.submit('jump, wait, jump, wait')), ['how high?'] * 2)

    @raises(ResponseFailure)
    def raises_failure_exception_when_sentinel_detected(self):
        r = FailingResponder(
            pattern='ju[^ ]{2}',
            response='how high?',
            failure_sentinel='lolnope',
        )
        # Behaves normally initially
        eq_(list(r.submit('jump')), ['how high?'])
        # But then!
        r.submit('lolnope')
