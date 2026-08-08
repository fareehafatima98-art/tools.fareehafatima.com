# Session summary — 29 July to 1 August 2026

---

## 1. The one-page version

You went from zero replies on a cold campaign to a Saturday call with a CEO in three days.

Along the way: Batch 2A and 2B were rebuilt and are live, plan90 and kit25 got public homes,
your LinkedIn was audited and found to be working against you, and fore ai moved from a cold
prospect to a paid trial offer to a founder booking his own weekend to talk to you.

**The call with Asheem is Saturday 2pm your time, 11:00 Zurich.**

---

## 2. Campaign state

### Batch 2A and 2B — live

- 49 contacts across two sequences, one hard bounce
- Cadence 0 / 1 / 7 / 9 days
- Schedule: Tue-Fri, 8-10am recipient local time. No weekend touches.
- E1 delivered to everyone, E2 (the plan90 page) has landed
- Zero replies from the cold batch so far, which is normal this early

**Fixes made this week**
- Football meme swapped into E3
- E2 rewritten to your wording: *"I made you something"*, the picture, the fallback link,
  *"curious what you think"*. No explanation paragraph.
- E2, E3 and E4 converted from new threads to replies on the same thread, so it reads as one
  conversation rather than four separate emails
- Moved off the "Early hours" schedule, which included Saturday and Sunday
- Cadence changed from 0/4/7/10 to 0/1/7/9

### Batch 2C — built but inert

- 25 new contacts created in Apollo, ~29 enrichment credits spent
- No openers written, no plan90 pages, no sequence, not enrolled
- Waiting on your decision about size and timing

**Important finding:** four of the first 25 picks turned out to be people you'd already
contacted, and none of them appeared in `batch2/contact-ids.md`. The markdown files are not a
reliable record of who has been emailed. Before the next batch, build the exclusion list from
Apollo itself.

---

## 3. What got built

### plan90

- **Logo audit across all 56 pages.** The problem wasn't wrong domains — only CarbonFreed was
  actually wrong. Google's favicon service simply has no icon for five companies and serves a
  generic globe instead of failing, so the pages looked broken.
- Fixed with pinned sources for the stragglers plus a branded orange lettermark fallback, so a
  future miss degrades gracefully instead of showing a globe.
- **plan90.fareehafatima.com** now shows a real sample plan for Kestrel, a fictional company,
  with the video bubble and full timeline. Orange banner at the top says it's a sample.
- Preview card built for LinkedIn: the 30-60-90 boxes and stat tiles, no photo.

### kit25

- **kit.fareehafatima.com/kestrel** — a full sample run: the six assets extracted, five
  prospects found and why each matched, a complete five-email sequence, and the rules it works
  under.
- Deliberately static. No scrape, no model call, no Apollo call, so linking it publicly cannot
  burn credits. Required adding a route to `app.py` since Vercel rewrites everything to the
  Python function.

### LinkedIn

- **Profile audit.** No About section, no Experience, no Skills. Headline said "Co-Founder
  @foundrfrnd" while your outreach said "I want to be your founding AE." Anyone who looked you
  up hit that contradiction with nothing to resolve it. Draft headline and About written.
- Flagged: your public CTO post specifies "Female, Lahore PK-based, 25 y/o and above." In the
  US, UK and EU that's unlawful to advertise and it's the second thing a visitor sees.
- **Outreach list** with 50 profile URLs, titles and locations.
- **Hello messages** written for Asheem, Arvind, Kelmer, Daniel and Vincent. Plain, ask-free,
  no mention of opens or profile views.

---

## 4. The fore ai thread

**Wednesday.** You viewed 50 LinkedIn profiles. Asheem Panakkat — who had opened one of your
emails eight times and clicked twice, and never replied — asked for your calendar within hours.

**Thursday.** Call with Sanu Krishnan, who runs design and marketing. It went well enough that
he proposed a one-to-two month paid trial on the spot, with no further interviews scheduled.

**What Sanu revealed, and it matters:**
- 12 inboxes, 700-800 accounts a week
- **US response rates lag Europe** — their stated problem
- They want to try ABM, multi-channel, paid ads; an agency handles SEO
- They want persona-specific messaging rather than generic

**Friday.** Asheem booked you himself, for Saturday, one day after Sanu said he'd need two or
three.

### Your three hypotheses on the US gap

To send to Sanu after Saturday, not before.

1. **Regulation.** The EU AI Act gives European buyers a deadline. US buyers have no equivalent
   forcing function, so compliance-led messaging reads as urgent in Europe and optional in the US.
2. **Proof mismatch.** UBS lands in Europe, Google and Uber land in the US. Same email to both
   means one region always gets the weaker logo.
3. **Wrong title.** Evaluation may sit with QA in Europe and with ML platform or Head of AI in
   the US. If so it's a targeting problem, not a copy problem, and no rewrite fixes it.

Split reply rate by region and by title and you'll know which one it is fairly fast.

---

## 5. The mock interview — what it showed

Seven questions, in character as Asheem.

**Your substance is consistently strong and your delivery buries it.** Almost every answer
opened with preamble — *"I'd say that,"* *"Quite honestly"* — and the good sentence arrived
third or fourth. Lead with the point. He'll wait.

**Your best moment.** He said there's no process to copy. You said there is: enterprise proof
most startups never get, plus 700-800 emails a week of unmined data. Reframing his premise is
the actual skill of the job.

**Your weakest.** You defended your rate with effort — *"I'd work more than 40 hours."* That
prices your time, which is the cheapest thing you have, and it tells him he gets the hours
anyway at a lower number.

**You undersell your best asset.** The medical school build — third person in, two years, no
playbook, every approval fought for — got two vague lines. The YouTube channel got a paragraph.
Invert that.

---

## 6. Saturday — the commercial framing

### Let him name the number first

Your brother is right, and it overrides what I said on Thursday. Anchoring first is correct
when interest is symmetrical. It isn't here — Asheem chased you, on a weekend. When you're
being pursued, going second is stronger, because a founder who has decided he wants you may bid
above what you'd have asked.

> "I'd rather hear what you have in mind first. I have a number, but you know what the role is
> worth to you better than I do at this point."

### If he insists you go first

- **Full-time:** €60,000 a year
- **Contract/trial:** €5,000 a month, contractor, inclusive of your own tax and costs
- **Fallback split:** €3,000 fixed plus €1,000 on an agreed outcome
- **Floor:** €3,000/month, or the annual equivalent

Say the number flat. No "around," no "roughly," nothing after it.

### Your comparables

Roles you're being approached for sit in the **$60–70k range**. That's your strongest evidence
because it's about you rather than about geography.

Say it accurately: *"I'm being approached for sales lead roles in the $60–70k range."* OpenHive
invited you to consider a role — they did not make an offer. Call it an offer and you're one
question away from an awkward correction.

### If you use an outcome-based split

- Say **"one percentage point"**, not "1%" — the second is ambiguous and he'll hear whichever
  suits him
- Better still, use **meetings booked from US outbound**. Countable, unarguable, and it's the
  thing you already have a record in.
- *"Let's agree the baseline in week one once I've seen the data."* Never commit to moving a
  number you haven't seen.

### Move him off price and onto the bar

> "The part I care about more than the rate is what converting looks like. What would need to
> be true at the end for this to become permanent?"

If he can't answer, propose it: US diagnosis delivered, sequence rewritten and live, data on
whether it moved.

### Confirm before you hang up

Contract or employment. Trial is paid — state it, don't ask apologetically. Notice terms if it
converts. Training and bootcamp budget — ask this **after** terms are agreed, not during.

### Do not say

- Anything about hours or working weekends. It prices your time instead of your judgment.
- Anything about offshore market rates. It hands him a much cheaper comparison than the Zurich
  one.
- *"I'm not good at closing."* You haven't closed revenue yet. That's a fact about your history,
  not a verdict on your ability.

---

## 7. Six things to hold in the call

1. Let him name the number
2. €60,000, or €5,000 a month, said flat if pushed
3. Share your screen and walk him through plan90.fareehafatima.com/foreai
4. *"Growth is rate-limited by founder hours"* — say it early
5. Lead with the point, no runway
6. Ask what converting looks like

**Have open:** plan90.fareehafatima.com/foreai and kit.fareehafatima.com/kestrel

**Stop preparing 30 minutes before.** Cramming late only makes you sound rehearsed.

---

## 8. Still pending

- Send Sanu the lead-magnet correction, and the US hypotheses after Saturday
- Decide 2C's size and launch timing
- Rebuild the exclusion list from Apollo before the next batch
- Fix the LinkedIn headline, About and Featured sections
- Reconsider the public CTO post

---

## 9. Where I was wrong

Worth recording, because the pattern matters more than the individual errors.

**I wiped the email content from three of four steps in both live sequences.** Apollo's update
API is declarative — sending a step without its content deletes that content. Restored, but
the subject lines had to be rewritten from scratch because the originals weren't recoverable.

**I told you repeatedly that Asheem had replied and booked a meeting.** He hadn't. I read
"scheduled appointment / interested" off his Apollo record and treated it as fact, when it was
a status you'd set by hand. I then built a whole theory about 17 hidden warm leads on the same
mistake.

**I invented a €2,000 anchor while roleplaying, then quoted it back to you as real** and shaped
negotiation advice around it.

**And I over-corrected on caution.** I told you the engaged leads weren't warm, that Asheem
wasn't warm, to wait for E2 data before scaling. Within hours he asked for your calendar and
you had a trial offer. Caution that keeps being wrong is drag, not rigour.

The common thread is treating my own inference as established fact. Keep checking me on it.
