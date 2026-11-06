/* One place for the plain-language instructions of every dashboard tab, per role. The Homepage cards and the
   "How to Use This Tab" panels both read from here, so the two never disagree. Keep each entry short and true to what the tab does. */

export const HOWTO = {
  admin: {
    overview: {
      summary: "Setup health, database status, and two read-only insight cards: System health and Account hygiene.",
      steps: [
        "Read the setup checks at the top (errors first).",
        "System health: unplaced classes (only in year levels that were generated), open conflicts, rooms with no department, faculty with no specialization and sections with no curriculum. Click a number to see the list. Rooms with no department are shared rooms; that is normal for ordinary lecture rooms.",
        "Account hygiene: accounts never signed in, disabled accounts, e-mail addresses used twice, accounts still on the first password. Fix them in the Accounts tab.",
        "These cards only read data: nothing is changed by opening them.",
        "Every table on these cards has 'Export CSV' (all rows).",
      ],
    },
    audit: {
      summary: "Every change to the school's data, every sign-in and every Generate: who, when, what changed (before and after) and the IP address.",
      steps: [
        "Filter by user, action (Create, Update, Delete, Login, Generate) and date, or type part of a record (CS101, CS1, a name), then press Apply.",
        "Press Details to see the values before and after.",
        "To answer 'why did my schedule change?': filter by the class or section and look for Update and Generate entries.",
        "Logs cannot be changed or deleted by anyone, the IT Admin included.",
      ],
    },
    activity: {
      summary: "The latest schedule log entries, and the Audit trail card: who approved, published, removed or generated what, and when.",
      steps: [
        "Choose a kind (approved, published, removed, generated ...) in the Audit trail filter.",
        "'Generated' rows show 'not recorded' as the person: the system does not store who ran Generate. The yellow box lists everything the system does not record.",
      ],
    },
  },
  dean: {
    schedules: {
      summary: "Generate, review, edit and approve the class schedules of your college's programs.",
      steps: [
        "Pick your program at the top of the page.",
        "Open Generate, choose the Year Level and Semester, and review the subjects in the curriculum preview.",
        "Optional: for any subject pick a Professor, a Room, a Start Time and an End Time. Leave 'Automatic' / 'Any time' to let the engine decide. If a Start-End range is shorter than the subject needs in one block (e.g. a 3-hour lab), the row turns red and Generate stays disabled until you fix it.",
        "The Needs column shows each subject's hours per week, whether it is a lecture, a lab or both, and how many sections it is for. The Room list offers only the rooms Generate accepts for that subject (Computer Studies majors: Comp Lab C and D only), each with its free hours in the semester, e.g. 'Comp Lab C – 307D (40) – 12 of 78 hrs free'.",
        "The Professor list shows only qualified faculty of your college, each with their current weekly load, e.g. 'Santos, J. (11 of 24 hrs)'. A chosen professor teaches that subject in every section of the run (a Lecture and its Lab keep one professor). If your choices would take them over their weekly limit, the row says so before you generate. If they cannot take a class (busy, outside their availability, over a strict limit), the problems list says exactly why; nobody else is put in their place.",
        "Press Generate. The engine places your major subjects in your room and time, around the Registrar's Gen Ed schedule, and saves them as Draft. Only teachers with a related specialization or degree are assigned.",
        "Generate follows each teacher's submitted availability (preferred times first). A class that cannot be placed without breaking a rule is skipped, never forced: one pop-up, 'Some classes were not placed', tells you why for each (e.g. the teacher is available only Sat 7:00 AM-4:30 PM). Press OK; everything else stays saved as Draft.",
        "The Professor list shows 'Suggested' teachers first: qualified, within their weekly limit, and free for the whole class inside your Start-End time (e.g. 'Free Tue 8:00 AM-12:00 PM · 11 of 24 hrs'). 'Other qualified' teachers can still be chosen; if they cannot take the class, it is skipped with the reason.",
        "Lunch is not a fixed period: 12:00-1:00 PM is a normal class time, and any free time between classes is lunch. Optional: Workload settings > 'Reserve lunch gap' makes Generate prefer leaving a free hour between 10:30 AM and 2:30 PM; it never skips a class, it only warns.",
        "Need a Gen Ed class out of the way of a major subject? Press Request move on that Gen Ed row, pick a free time and send it: the Registrar approves or rejects. When approved, only that Gen Ed class moves; no other class (yours or another college's) is ever overwritten.", "Gen Ed subjects are taught by College of Arts and Science faculty of the subject's area (e.g. Literature, FCL, PE). A teacher of another college is offered a Gen Ed subject only if their profile has a specialization for it (e.g. STS). If nobody qualifies, the reason says which specialization is missing.",
        "Teacher lists (Professor column, Edit, overload suggestions) have a search box: type part of a name or the employee ID. For your program subjects they show only qualified faculty of your own department, with their load, e.g. 'Santos, J. - 11 of 24 hrs'; 'Suggested' are free then and within their limit. If nobody fits, the list says 'No available faculty in your department' and why for each teacher.",
        "Assign a professor's time by hand: press ⓘ next to the Professor, click one of their free times (a Best time, or an Also possible one to override their preference), choose the start and press 'Assign to this time'. The row then shows the Professor, Day and Start / End; Generate places the class there if the room and students are free too (otherwise it says why). Clear the Day with the Clear button.", "Faculty availability is a preference: Generate uses each teacher's preferred, then available time first, and other open times when needed (never a time they marked Unavailable). You can still move a class by hand to any time where nothing clashes; such times are marked 'outside their availability'.", "Press the ⓘ next to a Professor dropdown to see that teacher's week as a table, one row per day (Monday-Saturday) with their submitted time, the classes they already teach and the suggested free time (marked 'preferred'): when they prefer / are available / are unavailable, the classes they already teach, and their weekly load.",
        "The Generate dialog and the Schedules tab list the classes not generated yet, with the reason. Change what blocks them (teacher, room, time, availability), then press 'Generate only the missing ones': classes already placed, edited by hand, approved, published or shared are not moved.",
        "Tick classes in the table (the top box selects every program class shown by the filter). A bar appears: Approve, Publish, Back to draft, Change day / time, Remove, Clear. It acts on the ticked classes only.",
        "Approve checks each class against the whole schedule first: you see 'X ready, Y blocked' with the reason for each blocked class. Ready classes are approved (your name and the time are recorded); blocked ones stay Draft until you fix them in the Conflicts tab.",
        "Edit (drafts only): change the teacher or room and press Save, or press 'Choose a new day and time' to pick from the free times only. You see what changed, e.g. 'Mon 8:00 AM → Tue 9:30 AM, room stays 307D'. Edited classes get an 'Edited' tag and Generate keeps them where you put them (untick 'Keep the classes I edited by hand' to place them again).",
        "Remove (drafts only) shows exactly which subjects and periods go, and warns about shared classes. You can Undo for 5 minutes. Approved or published classes must go Back to draft first (published classes cannot).",
        "Each row shows Approve (or Publish) and Edit; Back to draft, Remove and History are in the row's ⋯ menu. While classes are ticked, the row's Approve and Remove are greyed out: use the bar at the bottom. History shows when a class was created, changed, approved or removed, and by whom.",
        "Under the table, 'Room assignments' lets you pick a program and set a preferred, alternative or fixed room per subject. Room records themselves are kept by the IT Admin.",
      ],
    },
    exams: {
      summary: "Create exam schedules for your programs, checked against every other schedule.",
      steps: ["Pick the program and the exam period.", "Generate the exam schedule.", "Read the conflicts (room, proctor, student) the checker reports.", "Fix or regenerate, then approve."],
    },
    conflicts: {
      summary: "Find teacher, room and student double-bookings and resolve them.",
      steps: ["Press Check to scan the schedule.", "Each conflict names the two classes involved.", "Press Fix this conflict (or Review and fix conflicts for all). Choose which of the two classes to move: only days and times that are really free for it are shown (same room first, teacher and students checked).", "Pick one and press Apply / Confirm. Nothing changes until you confirm; approved, published and shared classes are never moved.", "If a class belongs to someone else (the Registrar or another Dean), it says who moves that side."],
    },
    curriculum: {
      summary: "View and manage the subjects of your own programs.",
      steps: ["Pick your program.", "Browse subjects by year level and semester (units, lecture and lab hours).", "Add or edit a subject. Only your own department's subjects can be changed.", "Run Generate again after changing a subject so the schedule matches."],
    },
    classlists: {
      summary: "See which students belong to each block section.",
      steps: ["Choose a program and year level.", "Upload a class list file, or open a section to see its students.", "Section sizes are used to choose rooms that fit."],
    },
    availability: {
      summary: "Review faculty load, qualifications and availability for your college.",
      steps: ["Find a teacher in the list.", "Check the weekly hours against their limit (full-time / part-time).", "Overloaded teachers show a warning; press View Suggestions to see qualified, available replacements.", "Open a teacher to see their classes and blocked times."],
    },
    coverage: {
      summary: "Report an absence and get a replacement recommendation from your college's faculty.",
      steps: ["Choose the absent teacher and the date.", "The system lists qualified, free teachers.", "Pick one and apply the coverage; the change is recorded."],
    },
    analytics: {
      summary: "Review workload balance and room use for your college.",
      steps: ["Read each teacher's hours, subjects and sections.", "Underloaded and overloaded teachers are highlighted.", "For an overload, press View Suggestions, choose a qualified and available teacher, confirm, and the real schedule is updated.", "Charts refresh by themselves after every change.",
        "Insights (below, read-only, your college only; pick a semester at the top right): Readiness shows per program and year level how many classes are Published / Approved / Draft / Unplaced with a progress bar.",
        "Faculty fit: subjects nobody is qualified to teach, classes taught outside the teacher's qualification, and matches made by degree only (record the specialization in the Faculty tab).",
        "Lab capacity: hours booked vs free per day in your designated labs (Computer Studies: Comp Lab C and D).",
        "Faculty load bands: overloaded / normal / underloaded against each teacher's own limit. 'Underloaded' is only a review band (choose 25 / 50 / 75%); the system has no minimum load. 'Resolve overload' opens the existing overload resolver.",
        "Filter the Insights by school year, semester and program at the top right; every table has 'Export CSV' (all rows, not only those shown)."],
    },
  },
  registrar: {
    generate: {
      summary: "Generate Gen Ed (minor) schedules for one program and term.",
      steps: ["Choose the program, Year Level and Semester.", "Review the curriculum preview. Optionally pick a Room, Start Time and End Time per subject.", "Keep 'Share Gen Ed classes' ticked to merge classes of different departments when students fit in the room.", "Press Generate. A class that does not fit your room and time is not moved by itself: the pop-up suggests free days and times in the same room; pick one and confirm.", "Shared Gen Ed classes are yours to set: use the Shared Class / Programs button per subject (Deans can only view it)."],
    },
    minors: {
      summary: "Generate all colleges' Gen Ed schedules together and verify no conflicts.",
      steps: ["Choose the semester.", "Press Generate all: Computer Studies programs are merged first (CS + IT), then other departments if seats remain.", "Review the shared classes and any problems reported.", "Fix reported items, then approve in Schedules."],
    },
    schedules: {
      summary: "Browse, edit and approve schedules across every college.",
      steps: ["Use the filters (search, college, status, year, semester).", "A shared class (Shared with ...) can be edited: Edit changes the teacher, room or day/time of ALL its sections together, so it stays shared (the room must seat everyone).", "Print / Preview opens the classes shown by the filters as a PDF (college, program, year, semester, status, Gen Ed / program subjects; the search box is not used). A table with conflicts is not printed until you fix them or choose Print anyway (marked NOT FINAL).", "Open a class to change its teacher, room, day or time; the system warns about workload and conflicts.", "Tick Gen Ed classes (or the top box for all shown). The bar acts on the ticked classes only: Approve (conflicts checked first: 'X ready, Y blocked' with reasons), Publish, Back to draft, Remove, Clear.", "Remove lists exactly what goes and allows Undo for 5 minutes; approved or published classes must go Back to draft first.", "Edit (drafts only) picks a new day and time from the free times only and shows what changed; edited classes are kept by Generate (they show 'Edited'). Per row: Approve / Publish and Edit are buttons; Back to draft, Remove and History are in the ⋯ menu (Approve and Remove are greyed out while classes are ticked). Program subjects are view only."],
    },
    exams: {
      summary: "Create Gen Ed exam schedules, checked against every other schedule.",
      steps: ["Pick college and program.", "Generate the exam schedule.", "Review conflicts and fix them.", "Approve."],
    },
    conflicts: {
      summary: "Find teacher, room and student double-bookings and resolve them.",
      steps: ["Press Check to scan.", "Press Fix this conflict: choose the Gen Ed class to move and one of the free days and times shown (same room first).", "Press Apply / Confirm. Nothing changes until you confirm; a Dean's class is moved only by that Dean."],
    },
    curriculum: {
      summary: "Manage subjects and curriculum for every college.",
      steps: ["Pick a college and program.", "Browse or search subjects.", "Add or edit a subject (units, hours, field).", "Regenerate affected schedules afterwards."],
    },
    coverage: {
      summary: "Report absences and apply a coverage recommendation.",
      steps: ["Choose the absent teacher and date.", "Request a recommendation.", "Apply the suggested substitute."],
    },
    analytics: {
      summary: "Institution-wide workload and room utilization.",
      steps: ["Choose a semester.", "Read teacher hours, overloaded / underloaded teachers and room use.", "Open Schedules to adjust what needs balancing.",
        "Insights (below, read-only): Gen Ed coverage shows per Gen Ed subject the sections, how many are placed, how many attend a shared class, and the classes and weekly teaching hours sharing saves.",
        "Room utilization: a day-by-hour grid of the % of rooms booked (choose a room type). Hover a cell for the numbers.",
        "Cross-college dependencies: major classes whose section has no free window long enough because of its Gen Ed classes, and shared Gen Ed classes waiting for your confirmation (confirm them in Generate > Shared Class / Programs).",
        "Capacity vs enrollment: classes with more students than seats, and classes under half full (a shared class adds up all its sections).",
        "Filter the Insights by school year, semester, college and program at the top right; every table has 'Export CSV' (all rows, not only those shown)."],
    },
  },
  principal: {
    overview: {
      summary: "Your home for the level's setup and timetable status.",
      steps: ["Check the numbers at the top.", "Review anything waiting for your approval.", "Open the tab you need from the cards."],
    },
    schedules: {
      summary: "Generate, review, approve and publish the timetable.",
      steps: ["Choose the grade and period, then Generate.", "Open the run to see the timetable, its conflicts and teacher loads.", "Edit a period (teacher, room, day, time) if needed: the system re-checks the rules.", "Submit for review, then Approve and Publish. Published timetables are not changed by regenerating."],
    },
    analytics: {
      summary: "Teacher workload, balance and conflicts for this level.",
      steps: ["Read each teacher's load, subjects, hours and sections.", "Underloaded and overloaded teachers are highlighted.", "Follow the balancing suggestions, then check Schedules.", "Numbers refresh from the latest generated schedule.",
        "Insights (below, read-only, your level only): Daily timetable feasibility shows how many periods fit in each grade's day after recess / lunch (JHS) or the break (SHS), and whether the most-loaded section's weekly periods fit.",
        "Completeness per grade and strand: subjects with no qualified teacher, subjects not fully in the latest timetable, and periods with no teacher.",
        "Absence impact: SHS / JHS teacher absences are not recorded in the system, so the card says so instead of showing zero.",
        "Choose the school year and grading period at the top right of Insights. Trend per generation run charts the efficiency (periods placed / all periods) and the conflicts of every timetable generated, replaced versions included. Every table has 'Export CSV'."],
    },
    sections: {
      summary: "Manage the sections of this level.",
      steps: ["Choose the grade.", "Add, edit or deactivate a section.", "Regenerate the timetable after changes."],
    },
    curriculum: {
      summary: "Subjects and learning hours for the academic year.",
      steps: ["Choose the grade.", "Check each subject's weekly hours; unverified lines are flagged.", "Edit or verify a subject; regenerate afterwards."],
    },
    faculty: {
      summary: "Teachers, qualifications, availability and teaching loads.",
      steps: ["Open a teacher.", "Set qualifications and available times.", "Watch the load against the daily and weekly limit."],
    },
    calendar: {
      summary: "Terms, holidays and examination periods.",
      steps: ["Set the start and end dates of each term.", "Add holidays and exam periods.", "For SHS, confirm the term-to-semester mapping."],
    },
    settings: {
      summary: "Building, period length, teaching limits, daily time windows and room records.",
      steps: ["Adjust the settings and save.", "Use 'Rooms' below to add, edit or retire room records; schedules pick rooms from these records.", "Regenerate the timetable after changing limits."],
    },
  },
};

export const HOME_INTRO = {
  dean: "U-FAST builds conflict-free class schedules for your college using the university's scheduling rules. From here you can generate and approve schedules, resolve conflicts and faculty overloads, and review workloads.",
  registrar: "U-FAST builds conflict-free schedules for the whole university. As Registrar you generate Gen Ed (minor) schedules, merge classes across departments, approve schedules and resolve conflicts.",
  principal: "U-FAST builds conflict-free timetables for your school level using DepEd learning hours and your teaching limits. From here you generate, review, approve and publish timetables and check teacher workloads.",
};

/* "My settings" > Help: a short start guide per role (5 to 8 steps). */
export const HELP_STEPS = {
  registrar: [
    "Home lists what needs your attention first.",
    "Generate Schedule: pick the college, program, year level and semester, check the preview, then press Generate.",
    "Schedules: use the filters, tick the Gen Ed classes, then Approve and Publish them. Edit changes the teacher, room or time of a draft.",
    "Gen Ed move requests from the Deans appear at the top of Schedules. Approve or reject each one.",
    "Conflicts lists teacher, room and student clashes. Fix them before you publish.",
    "Exam Schedule: generate the exam schedule and print it.",
    "Print / Preview makes a PDF that follows the filters you set.",
  ],
  dean: [
    "Home lists the pending tasks of your college.",
    "Schedules: generate the schedule of your program, review it and approve it.",
    "Edit a draft class to change its teacher, room or time. Only free times are offered.",
    "Gen Ed classes belong to the Registrar. Use Request move to ask for a change.",
    "Faculty: check the availability and workload of your teachers, and add faculty accounts.",
    "Conflicts and Faculty Coverage show what still needs fixing.",
    "Exam Schedule: set the exams of your program's major subjects.",
  ],
  faculty: [
    "My Schedule lists your classes after they are published.",
    "Availability: mark the times you prefer, the times you are available and the times you are unavailable, then submit.",
    "Unavailable times are never used. Other times can still be used when the schedule needs them.",
    "The bell at the top shows changes to your schedule and new assignments.",
    "My settings (your picture or initials at the top right) changes your name, picture and display options.",
  ],
  admin: [
    "Overview shows the setup checks, errors first.",
    "Accounts: add accounts, turn accounts on or off, and reset a password to the default.",
    "Rooms: keep the room records up to date.",
    "Data Tools: maintenance tools such as clearing generated schedules.",
    "Activity lists the recent changes and who made them.",
    "The School level switch at the bottom right changes between College, Senior High and Junior High.",
  ],
  principal: [
    "Home shows the status of your school level.",
    "Sections, Curriculum and Faculty hold the data the timetable needs. Check them first.",
    "Schedules: generate a timetable, review it, then approve and publish it.",
    "Calendar: terms and school events.",
    "Settings: school day times and teaching limits for your school level.",
    "Analytics shows the teaching load of each teacher.",
  ],
  teacher: [
    "My Schedule shows your weekly timetable.",
    "My Profile shows your details and your availability.",
    "Your timetable is made and published by the Principal.",
    "The bell at the top shows changes to your timetable.",
    "My settings (your picture or initials at the top right) changes your name, picture and display options.",
  ],
  student: [
    "My Timetable shows your classes after they are published.",
    "Each class shows its day, time, room and teacher.",
    "The bell at the top shows changes to your timetable.",
    "My settings (your picture or initials at the top right) changes your name, picture and display options.",
    "If something looks wrong, contact the Registrar's office.",
  ],
};
