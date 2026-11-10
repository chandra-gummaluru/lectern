# Lectern

Lectern is one place to run a course. For each course offering (a course in one term, like CSC258 in Fall 2026) it keeps the **course page**, the **gradebook** and the **exams** together, so they stay in step with each other.

## What you can do with it

- **Build your course page.** Add weekly activities, announcements, evaluations and your teaching team, and Lectern turns them into a course website with tabs for *This week*, *Announcements*, *Activities*, *Evaluations* and *About*. Choose which tabs are public and which are for signed-in students only. You can embed the page in Quercus.
- **Keep your gradebook.** Set up evaluations (weights, due dates, "best N of M", makeups), import your class list from Quercus or ACORN, and enter marks. The marking scheme appears on your course page automatically, and each evaluation shows up in the week it's due.
- **Write exams and handouts.** From any evaluation, open its test or assignment and write it in place. Its total marks feed straight back into the gradebook.
- **Handle accommodation requests.** Students request an accommodation for a missed evaluation from the course page. You approve or reject it in Lectern, and the student is emailed the decision.
- **Work as a team.** Add instructors and TAs to an offering. Instructors can do everything you can; TAs can see the gradebook and enter marks, but can't change the course setup.

## Who sees what

- **Your course page** is the only thing that's ever published. You decide which of its tabs anyone can see and which need a sign-in.
- **Grades, exams and accommodation requests** are private. Only you and the teaching team you've added can see them.
- **Students** sign in to the course page with their email and a one-time code. They see their own requests, never anyone else's or the gradebook.

## Getting started

1. **Get an invitation.** Lectern is invite-only. Your institution's Lectern administrator sends you an email invitation (or an instructor does, if you're joining their teaching team).
2. **Create your account.** Open the link, then choose your name, a password and the address for your course pages. We recommend turning on two-factor sign-in under **Your account**.
3. **Add a course offering** from Home, then fill in its course page, evaluations and class list.
4. **Share your course page** with students: send them its link from the Students card, or embed it in Quercus.

Your work is saved on Lectern's server, and earlier versions are kept, so a mistake can be undone.

To use Lectern as an app, in its own window with its own icon, choose **Install Lectern** from the account menu (top right). On an iPhone or iPad, it shows how to add Lectern to your Home Screen.

## For administrators

This section is for whoever sets up Lectern for an institution or department. You'll need a server (or any computer) with Python 3 and git, and an HTTPS address for it (for example through a Cloudflare Tunnel or nginx).

### Install

```
git clone https://github.com/chandra-gummaluru/lectern.git ~/apps/lectern
~/apps/lectern/new-lectern.sh
```

This installs Lectern and asks a few questions:

1. **Where it lives:** its public address (e.g. `https://lectern.example.edu/`), its port and your institution's name.
2. **Email** (optional, can be set up later): an SMTP login, used for invitations, password resets and students' sign-in codes.
3. **The first administrator:** your email, name and password, plus a two-factor app (scan the QR code shown in the terminal).

Run `python app.py setup` again at any time to change a setting.

### Start it

```
python app.py
```

On a server, run it under tmux or systemd so it keeps running.

### Invite people

Sign in to the admin panel at `/admin` (e.g. `https://lectern.example.edu/admin`) and invite instructors by email, starting with yourself: your administrator login and your Lectern account are separate.

From the admin panel you can also see every account, sign someone out, reset their two-factor sign-in if they lose their phone, turn an account off or delete it, and change the email settings. To add another administrator, run `python app.py admin their@email` on the server.

### Look after it

- **Back up the `data/` folder** regularly. It holds every account and course, and the key that two-factor sign-in depends on.
- **Email is needed** for invitations, password resets and students signing in. Without it, those features won't work.

All settings, deployment details and how Lectern works inside are in [docs/developers.md](docs/developers.md).
