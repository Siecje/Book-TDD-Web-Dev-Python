[[chapter_fixtures_and_debugging_staging]]
Test Fixtures, Server-Side Debugging, and a Decorator for Explicit Waits
------------------------------------------------------------------------

[%autowidth,float="right",caption=,cols="2"]
|=======
2+|Chapter info
|shortname:|chapter_fixtures_and_debugging_staging
|=======

WARNING: Major update released for Selenium 3.
    If you started this book on or before Jan 30th 2017,
    be aware: chapters have been renumbered,
    so check this is the one you think it is,
    and have a look at the new <<chapter_explicit_waits_1>>
    for an indication of the changes you'll need in your FTs.
    You should do a `pip install --upgrade selenium` too.


Now that we have a functional authentication system, we want to use it to
identify users, and be able to show them all the lists they have created.

To do that, we're going to have to write FTs that have a logged-in user. Rather
than making each test go through the (time-consuming) login email dance, we
want to be able to skip that part.

((("functional tests/testing (FT)", "vs. unit tests", sortas="unittests")))
((("unit tests", "vs. functional tests", sortas="functionaltests")))
This is about separation of concerns.  Functional tests aren't like unit tests,
in that they don't usually have a single assertion. But, conceptually, they
should be testing a single thing.  There's no need for every single FT to test
the login/logout mechanisms. If we can figure out a way to "cheat" and skip
that part, we'll spend less time waiting for duplicated test paths.

TIP: Don't overdo de-duplication in FTs.  One of the benefits of an FT is that
     it can catch strange and unpredictable interactions between different
     parts of your application.


NOTE: This chapter has only just been rewritten for the new edition, so let me
    know via obeythetestinggoat@gmail.com if you spot any problems or have any
    suggestions for improvement!


Skipping the Login Process by Pre-creating a Session
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

((("fixtures", "in functional tests")))
((("authentication", "pre-authentication", id="ix_preauthent", range="startofrange")))
It's quite common for a user to return to a site and still have a cookie, which
means they are "pre-authenticated", so this isn't an unrealistic cheat at all.
Here's how you can set it up:

[role="sourcecode"]
.functional_tests/test_my_lists.py
[source,python]
----
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore
from .base import FunctionalTest
User = get_user_model()


class MyListsTest(FunctionalTest):

    def create_pre_authenticated_session(self, email):
        user = User.objects.create(email=email)
        session = SessionStore()
        session[SESSION_KEY] = user.pk #<1>
        session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session.save()
        ## to set a cookie we need to first visit the domain.
        ## 404 pages load the quickest!
        self.browser.get(self.server_url + "/404_no_such_url/")
        self.browser.add_cookie(dict(
            name=settings.SESSION_COOKIE_NAME,
            value=session.session_key, #<2>
            path='/',
        ))
----

<1> We create a session object in the database.  The session key is the
    primary key of the user object (which is actually their email address).

<2> We then add a cookie to the browser that matches the session on the
    server--on our next visit to the site, the server should recognise
    us as a logged-in user.

((("cookies")))
((("session key")))
Note that, as it is, this will only work because we're using
`LiveServerTestCase`, so the `User` and `Session` objects we create will end up in
the same database as the test server.  Later we'll need to modify it so that it
works against the database on the staging server too.
((("test fixtures")))
((("Django", "test fixtures")))
((("JSON fixtures")))


.Django Sessions: How a User's Cookies Tell the Server She Is Authenticated
**********************************************************************

'Being an attempt to explain sessions, cookies, and authentication in Django.'
((("sessions")))
((("cookies")))
((("authentication","in Django", sortas="Django")))
((("Django", "authentication in")))

Because HTTP is stateless, servers need a way of recognising different clients
with 'every single request'. IP addresses can be shared, so the usual
solution is to give each client a unique session ID, which it will store in a
cookie, and submit with every request.  The server will store that ID somewhere
(by default, in the database), and then it can recognise each request that
comes in as being from a particular client.

If you log in to the site using the dev server, you can actually take a look at
your session ID by hand if you like.  It's stored under the key `sessionid` by
default. See <<session-cookie-screenshot>>.

[[session-cookie-screenshot]]
.Examining the session cookie in the Debug toolbar
image::images/twdp_1601.png[scale="80"]

//TODO: update screenshot for non-persona

These session cookies are set for all visitors to a Django site, whether
they're logged in or not.

When we want to recognise a client as being a logged-in and authenticated user,
again, rather asking the client to send their username and password with every
single request, the server can actually just mark that client's session as
being an authenticated session, and associate it with a user ID in its
database.

A session is a dictionary-like data structure, and the user ID is stored under
the key given by `django.contrib.auth.SESSION_KEY`.  You can check this out
in a `manage.py` console if you like:

[role="skipme small-code"]
[subs="specialcharacters,macros"]
----
$ pass:quotes[*python manage.py shell*]
[...]
In [1]: from django.contrib.sessions.models import Session

# substitute your session id from your browser cookie here
In [2]: session = Session.objects.get(
    session_key="8u0pygdy9blo696g3n4o078ygt6l8y0y"
)

In [3]: print(session.get_decoded())
{'_auth_user_id': 'obeythetestinggoat@gmail.com', '_auth_user_backend':
'accounts.authentication.PasswordlessAuthenticationBackend'}
----

You can also store any other information you like on a user's session,
as a way of temporarily keeping track of some state. This works for
non-logged-in users too.  Just use `request.session` inside any
view, and it works as a dict. There's more information in the
https://docs.djangoproject.com/en/1.10/topics/http/sessions/[Django docs on
sessions].

**********************************************************************


Checking It Works
^^^^^^^^^^^^^^^^^

To check it works, it would be good to use some of the code from our previous
test.  Let's make a couple of functions called `wait_to_be_logged_in` and
`wait_to_be_logged_out`. To access them from a different test, we'll need
to pull them up into `FunctionalTest`. We'll also tweak them slightly so that
they can take an arbitrary email address as a parameter:

[role="sourcecode"]
.functional_tests/base.py (ch18l002)
[source,python]
----
class FunctionalTest(StaticLiveServerTestCase):
    [...]

    def wait_to_be_logged_in(self, email):
        self.wait_for(
            lambda: self.browser.find_element_by_link_text('Log out')
        )
        navbar = self.browser.find_element_by_css_selector('.navbar')
        self.assertIn(email, navbar.text)


    def wait_to_be_logged_out(self, email):
        self.wait_for(
            lambda: self.browser.find_element_by_name('email')
        )
        navbar = self.browser.find_element_by_css_selector('.navbar')
        self.assertNotIn(email, navbar.text)
----


Hm, that's not bad, but I'm not quite happy with the amount of duplication
of `wait_for` stuff in here.  Let's make a note to come back to it, and
get these helpers working.

[role="scratchpad"]
*****
* 'Clean up wait_for stuff in base.py'
*****


First we use them in 'test_login.py':


[role="sourcecode"]
.functional_tests/test_login.py (ch18l003)
[source,python]
----
    def test_can_get_email_link_to_log_in(self):
        [...]
        # she is logged in!
        self.wait_to_be_logged_in(email=TEST_EMAIL)

        # Now she logs out
        self.browser.find_element_by_link_text('Log out').click()

        # She is logged out
        self.wait_to_be_logged_out(email=TEST_EMAIL)
----

Just to check we haven't broken anything, we rerun the login test:


[subs="specialcharacters,macros"]
----
$ pass:quotes[*python manage.py test functional_tests.test_login*]
[...]
OK
----

And now we can write a placeholder for the "My Lists" test, to see if
our pre-authenticated session creator really does work:

[role="sourcecode"]
.functional_tests/test_my_lists.py (ch18l004)
[source,python]
----
    def test_logged_in_users_lists_are_saved_as_my_lists(self):
        email = 'edith@example.com'
        self.browser.get(self.server_url)
        self.wait_to_be_logged_out(email)

        # Edith is a logged-in user
        self.create_pre_authenticated_session(email)
        self.browser.get(self.server_url)
        self.wait_to_be_logged_in(email)
----

That gets us:

[subs="specialcharacters,macros"]
----
$ pass:quotes[*python manage.py test functional_tests.test_my_lists*]
[...]
OK
----

That's a good place for a commit:

[subs="specialcharacters,quotes"]
----
$ *git add functional_tests*
$ *git commit -m "test_my_lists: precreate sessions, move login checks into base"*
----
(((range="endofrange", startref="ix_preauthent")))
(((range="endofrange", startref="ix_staging_database")))


.JSON Test Fixtures Considered Harmful
*******************************************************************************
When we pre-populate the database with test data, as we've done here with the
`User` object and its associated `Session` object, what we're doing is setting
up a "test fixture".
((("JSON fixtures")))

Django comes with built-in support for saving database objects as JSON (using
the `manage.py dumpdata`), and automatically loading them in your test runs
using the `fixtures` class attribute on `TestCase`.

More and more people are starting to say:
http://bit.ly/1kSTyrb[don't use JSON fixtures].
They're a nightmare to maintain when your model changes.  Plus it's difficult
for the reader to tell which of the many attribute values specified in the
JSON are critical for the behaviour under test, and which are just filler.
Finally, even if tests start out sharing fixtures, sooner or later one
test will want slightly different versions of the data, and you end up copying
the whole thing around to keep them isolated, and again it's hard to tell
what's relevant to the test and what is just happenstance.

It's usually much more straightforward to just load the data directly
using the Django ORM.

TIP: Once you have more than a handful of fields on a model, and/or several
    related models, even using the ORM can be cumbersome.  In this case,
    there's a tool that lots of people swear by called
    https://factoryboy.readthedocs.org/[`factory_boy`].

*******************************************************************************


Our final explicit wait helper:  a wait decorator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We've used decorators a few times in our code so far, it's time to learn
how they actually work by making one of our own.

First, let's imagine how we might want our decorator to work.  It would be
nice to be able to replace all the custom wait/retry/timeout logic in
`wait_for_row_in_list_table` and the in-line `self.wait_fors` in the
`wait_to_be_logged_in/out`.   Something like this would look lovely:


[role="sourcecode"]
.functional_tests/base.py (ch18l005)
[source,python]
----
    @wait
    def wait_for_row_in_list_table(self, row_text):
        table = self.browser.find_element_by_id('id_list_table')
        rows = table.find_elements_by_tag_name('tr')
        self.assertIn(row_text, [row.text for row in rows])


    @wait
    def wait_to_be_logged_in(self, email):
        self.browser.find_element_by_link_text('Log out')
        navbar = self.browser.find_element_by_css_selector('.navbar')
        self.assertIn(email, navbar.text)


    @wait
    def wait_to_be_logged_out(self, email):
        self.browser.find_element_by_name('email')
        navbar = self.browser.find_element_by_css_selector('.navbar')
        self.assertNotIn(email, navbar.text)
----


Are you ready to dive in?  Although decorators are quite difficult to
wrap your head around (I know it took me a long time before I was
comfortable with them, and I still have to think about them quite
carefully whenever I make one), the nice thing is that we've already
dipped our toes into functional programming in our `self.wait_for`
helper function.  That's a function that takes another function as
an argument, and a decorator is the same.  The difference is that the
decorator doesn't actually execute any code itself -- it returns a
modified version of the function that it was given.

Our decorator wants to return a new function which will keep calling
the function it was given, catching our usual exceptions, until a
timeout occurs.  Here's a first cut:


[role="sourcecode"]
.functional_tests/base.py (ch18l006)
[source,python]
----
def wait(fn):  #<1>
    def modified_fn():  #<3>
        start_time = time.time()
        while True:  #<4>
            try:
                return fn()  #<5>
            except (AssertionError, WebDriverException) as e:  #<4>
                if time.time() - start_time > MAX_WAIT:
                    raise e
                time.sleep(0.5)
    return modified_fn  #<2>
----

<1> A decorator is a way of modifying a function; it takes a function
    an argument...

<2> and returns another function as the modified (or "decorated") version.

<3> Here's where we create our modified function.

<4> And here's our familiar loop, which will keep going, catching the usual
    exceptions, until our timeout expires

<5> And as always, we call our function and return immediately if there are
    no exceptions.


That's 'almost' right, but not quite;  try running it?


[subs="specialcharacters,macros"]
----
$ pass:quotes[*python manage.py test functional_tests.test_my_lists*]
[...]
    self.wait_to_be_logged_out(email)
TypeError: modified_fn() takes 0 positional arguments but 2 were given
----


Unlike in `self.wait_for`, the decorator is being applied to functions
that have arguments:



[role="sourcecode currentcontents"]
.functional_tests/base.py
[source,python]
----
    @wait
    def wait_to_be_logged_in(self, email):
        self.browser.find_element_by_link_text('Log out')
----

`wait_to_be_logged_in` takes `self` and `email` as positional arguments.
But when it's decorated, it's replaced with `modified_fn`, which takes
no arguments.  How do we magically make it so our `modified_fn` can handle
the same arguments as whatever `fn` the decorator gets given has?

The answer is a bit of Python magic, `*args` and `**kwargs`, more formally
known as
https://docs.python.org/3/tutorial/controlflow.html#keyword-arguments["variadic
arguments"], apparently (I only just learned that).



[role="sourcecode"]
.functional_tests/base.py (ch18l007)
[source,python]
----
def wait(fn):
    def modified_fn(*args, **kwargs):  #<1>
        start_time = time.time()
        while True:
            try:
                return fn(*args, **kwargs)  #<2>
            except (AssertionError, WebDriverException) as e:
                if time.time() - start_time > MAX_WAIT:
                    raise e
                time.sleep(0.5)
    return modified_fn
----

<1> Using `*args` and `**kwargs`, we specify that `modified_fn` may take
    any arbitrary positional and keyword arguments

<2> As we've captured them in the function definition, we make sure to
    pass those same arguments to `fn` when we actually call it.

One of the fun things this can be used for is to make a decorator that changes
the arguments of a function.  But we won't get into that now.  The main thing
is that our decorator now works:


[subs="specialcharacters,macros"]
----
$ pass:quotes[*python manage.py test functional_tests.test_my_lists*]
[...]
OK
----


And do you know what's truly satisfying?  We can use our `wait` decorator
for our `self.wait_for` helper as well!  Like this:


[role="sourcecode"]
.functional_tests/base.py (ch18l008)
[source,python]
----
    @wait
    def wait_for(self, fn):
        return fn()
----


Lovely!  Now all our wait/retry logic is encapsulated in a single place,
and we have a nice easy way of applying those waits, either inline in our
FTs using `self.wait_for`, or on any helper function using the `@wait`
decorator.

In the next chapter we'll try and deploy our code to staging, and
use the pre-authenticated session fixtures on the server.  As we'll see
it'll help us catch a little bug or two!
((("functional tests/testing (FT)", "de-duplication")))
((("test fixtures")))
((("JSON fixtures")))
((("Django", "management commands")))


.Lessons learned
*******************************************************************************

Decorators are nice::
    Decorators can be a great way of abstracting out different levels of
    concerns.  They let us write our test assertions without having to
    think about waits at the same time.

De-duplicate your FTs, with caution::
    Every single FT doesn't need to test every single part of your application.
    In our case, we wanted to avoid going through the full login process for
    every FT that needs an authenticated user, so we used a test fixture to
    "cheat" and skip that part. You might find other things you want to skip
    in your FTs.  A word of caution however: functional tests are there to
    catch unpredictable interactions between different parts of your
    application, so be wary of pushing de-duplication to the extreme.

Test fixtures::
    Test fixtures refers to test data that needs to be set up as a precondition
    before a test is run--often this means populating the database with some
    information, but as we've seen (with browser cookies), it can involve other
    types of preconditions.

Avoid JSON fixtures::
    Django makes it easy to save and restore data from the database in JSON
    format (and others) using the `dumpdata` and `loaddata` management
    commands.  Most people recommend against using these for test fixtures,
    as they are painful to manage when your database schema changes. Use the
    ORM, or a tool like https://factoryboy.readthedocs.org/[factory_boy].

*******************************************************************************



Stuff from the old edition that we might want to save
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using Hierarchical Logging Config
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

NOTE: this section has not yet been adapted to the new version, feel free to
    ignore it

((("logging configuration", id="ix_loggingconfig", range="startofrange")))
When we hacked in the `logging.warning` earlier, we were using the root logger.
That's not normally a good idea, since any third-party package can mess with the
root logger.  The normal pattern is to use a logger named after the file you're
in, by using:

[role="skipme"]
[source,python]
----
logger = logging.getLogger(__name__)
----

Logging configuration is hierarchical, so you can define "parent" loggers for
top-level modules, and all the Python modules inside them will inherit that
config.

Here's how we add a logger for both our apps into 'settings.py':

[role="sourcecode skipme"]
.superlists/settings.py
[source,python]
----
LOGGING = {
   'version': 1,
   'disable_existing_loggers': False,
   'handlers': {
       'console': {
           'level': 'DEBUG',
           'class': 'logging.StreamHandler',
       },
   },
   'loggers': {
        'django': {
            'handlers': ['console'],
        },
        'accounts': {
            'handlers': ['console'],
        },
        'lists': {
            'handlers': ['console'],
        },
    },
    'root': {'level': 'INFO'},
}
----

Now 'accounts.models', 'accounts.views', 'accounts.authentication', and all
the others will inherit the `logging.StreamHandler` from the parent 'accounts'
logger.

Unfortunately, because of Django's project structure, there's no
way of defining a top-level logger for your whole project (aside from using
the root logger), so you have to define one logger per app.


Here's how to write a test for logging behaviour:

[role="sourcecode skipme"]
.accounts/tests/test_authentication.py (ch18l023)
[source,python]
----
import logging
[...]

@patch('accounts.authentication.requests.post')
class AuthenticateTest(TestCase):
    [...]

    def test_logs_non_okay_responses_from_persona(self, mock_post):
        response_json = {
            'status': 'not okay', 'reason': 'eg, audience mismatch'
        }
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = response_json  #<1>

        logger = logging.getLogger('accounts.authentication')  #<2>
        with patch.object(logger, 'warning') as mock_log_warning:  #<3>
            self.backend.authenticate('an assertion')

        mock_log_warning.assert_called_once_with(
            'Persona says no. Json was: {}'.format(response_json)  #<4>
        )
----

<1> We set up our test with some data that should cause some logging.

<2> We retrieve the actual logger for the module we're testing.

<3> We use `patch.object` to temporarily mock out its warning function,
    by using `with` to make it a 'context manager' around the function we're
    testing.

<4> And then it's available for us to make assertions against.

That gives us:

[role="skipme"]
[subs="specialcharacters,macros"]
----
AssertionError: Expected 'warning' to be called once. Called 0 times.
----

Let's just try it out, to make sure we really are testing what we think
we are:

[role="sourcecode skipme"]
.accounts/authentication.py (ch18l024)
[source,python]
----
import logging
logger = logging.getLogger(__name__)
[...]

        if response.ok and response.json()['status'] == 'okay':
            [...]
        else:
            logger.warning('foo')
----

We get the expected failure:


[role="skipme"]
[subs="specialcharacters,macros"]
----
AssertionError: Expected call: warning("Persona says no. Json was: {'status':
'not okay', 'reason': 'eg, audience mismatch'}")
Actual call: warning('foo')
----

And so we settle in with our real implementation:

[role="sourcecode skipme"]
.accounts/authentication.py (ch18l025)
[source,python]
----
    else:
        logger.warning(
            'Persona says no. Json was: {}'.format(response.json())
        )
----


[role="skipme"]
[subs="specialcharacters,macros"]
----
$ pass:quotes[*python manage.py test accounts*]
[...]
Ran 15 tests in 0.033s

OK
----

You can easily imagine how you could test more combinations at this point,
if you wanted different error messages for `response.ok != True`, and so on.

.More notes
*******************************************************************************

Use loggers named after the module you're in::
    The root logger is a single global object, available to any library that's
    loaded in your Python process, so you're never quite in control of it.
    Instead, follow the `logging.getLogger(__name__)` pattern to get one that's
    unique to your module, but that inherits from a top-level configuration you
    control.

Test important log messages::
    As we saw, log messages can be critical to debugging issues in production.
    If a log message is important enough to keep in your codebase, it's
    probably important enough to test.  We follow the rule of thumb that
    anything above `logging.INFO` definitely needs a test.  Using
    `patch.object` on the logger for the module you're testing is one
    convenient way of unit testing it.

*******************************************************************************