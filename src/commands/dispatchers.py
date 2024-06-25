"""
Dispatchers are classes that take a pattern of syntax used for a command and map it
to the behaviors that we want to occur. Each dispatcher should take a regex pattern
that it is trying to match and a callable that will be invoked with args/kwargs. The
callable can be a method of an object that is targeted by our args, found via a search
function.

For example, suppose we want to create a command for 'look', which has three patterns
for its usage:
"look" with no arguments will examine the character's room.
"look <target>" will examine a given object matching the target.
"look <target>'s <possession>" will examine an object in the inventory of the target.

Each of these is a regex pattern that will be captured by a dispatcher object with
the behaviors that we want to create: calling a method (say, 'perceived()') in an
object with our caller passed in, as well as possible other args/kwargs. Each of these
will be a Dispatcher object that is added to a list in a command, lke so:

# inside our Look command
dispatchers = [
    LocationMethodDispatcher(r"^$", method=ArxRoom.perceived,
        search_function=current_location),
    TargetMethodDispatcher(r"^(?P<target_name>.+)$",
        method=ArxObject.perceived, search_function=local_search),
]

Each dispatcher is instantiated and saved in that list. When parse() is run, we find
which dispatcher, if any, matches our pattern, as well as binding them to our current
command instance. The found dispatcher is then assigned to self.found_dispatcher.
Later, if no found_dispatcher is present, we'll return an invalid usage error to the
user with a list of proper syntax. Note that the order of the dispatchers is
significant - much like urls.py for Django, we match the first pattern found then quit,
so you must make sure you go from more specific to more general.

search_function in the dispatcher is responsible for finding the instance object that
we'll call the method on, and any other targets we might pass into it. We'll assume
that the search_function will handle the case of the target being a possession to
find the correct target for the method. We won't try to determine any permissions of
whether the viewer is permitted to view the target at this stage: that should always
take place in the called method, not the search stage or the command stage. If they're
not permitted to view the target, then it will raise a CommandError that gives the same
response as a failed search.

"""
