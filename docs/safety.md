# Safety

HireEmber submits job applications for you, so it follows a short set of rules. This page lists
them, where your data goes and where your keys live. Under NFR-12 it changes in the same pull
request as the behaviour it describes.

## Forms and accounts

- **SAF-1:** the agent never types a password, token, payment detail or government ID into a form.
  A field of that kind sends the ticket to the human gate (the queue of tickets blocked for you).
- **SAF-2:** the agent does not create accounts or sign in. You do both, then mark the ticket ready.
- **SAF-3:** it does not bypass CAPTCHAs or bot checks and calls no solving service. The ticket
  stops at the human gate with the browser left on that page.

## Where it will not go

- **SAF-4:** LinkedIn is never read from or applied through. Discovery and the apply stage reject
  LinkedIn addresses.
- **SAF-12:** sites you mark as manual-only are never automated.

## What it submits

- **SAF-5:** every answer submitted traces to the answer bank or the profile. The attempt log lists
  each field with the source of its value.
- **SAF-6:** tailored documents contain no employer, project, school, metric or skill outside your profile.
- **SAF-11:** text on a job page is data. The agent does not follow instructions found on a page or
  enter data the form does not ask for.

## Browser and tools

- **SAF-7:** the agent runs only in a browser profile created for it, never your main profile.
- **SAF-10:** it loads only browser tools and the ticket's files. Mail tools load only if the
  email-application fallback is enabled.
- **SAF-9:** applications per day and per company are limited, with a wait between submissions.

## Where data goes

- **SAF-8:** the dashboard binds to 127.0.0.1 only, so it is not reachable from another device.
- Data leaves your machine only through the model provider you configured and the company sites you
  apply to.
- There is no telemetry: HireEmber sends no usage data, analytics or crash reports anywhere.
- Logs for each run and each apply attempt, and the model and token counts for each ticket, stay in
  your data folder (`~/.hireember`). Log files older than 90 days are deleted when a run starts.

## Where keys live

API keys live in the `.env` file in your data folder. Git ignores `.env`; `.env.example` holds no
real keys. Keys are never stored in the database and are redacted from log lines.

## Human gate

Anything the agent may not or cannot do ends at the human gate: the ticket is blocked for human,
queued on the dashboard with the reason and a link, and nothing further happens until you act.
