"""Textvorrat für den Wechseltext der Startseite (Deutsch und Englisch).

Die Paare stehen bewusst hier und nicht in den ``.po``-Dateien (zu groß, eigene Redaktion; siehe
``docs/i18n.md``). Gewählt wird über die aktive Sprache.

Jeder Eintrag ist ein Dict ``{"art", "de", "en", "tageszeit", "wochentage", "jahreszeit"}``:

- ``art``: ``spruch`` | ``weisheit`` | ``fakt`` | ``gruss``
- ``tageszeit``: ``morgen`` | ``mittag`` | ``nachmittag`` | ``abend`` | ``nacht`` | ``egal``
- ``wochentage``: ``None`` (jeder Tag) oder Tupel mit 0 = Montag … 6 = Sonntag
- ``jahreszeit``: ``fruehling`` | ``sommer`` | ``herbst`` | ``winter`` | ``egal``

Redaktionelle Regeln: kindgerecht (6-14 Jahre), nie beleidigend, keine Namen, keine Zitate
lebender Personen, Fakten nur gut gesichert (im Zweifel weggelassen), höchstens ein Emoji,
höchstens ca. 90 Zeichen.
"""

ARTEN = ("spruch", "weisheit", "fakt", "gruss")
TAGESZEITEN = ("morgen", "mittag", "nachmittag", "abend", "nacht", "egal")
JAHRESZEITEN = ("fruehling", "sommer", "herbst", "winter", "egal")
MAX_LAENGE = 100

# Kurzschreibweise in den Listen: (de, en) oder (de, en, {"t": Tageszeit, "w": (Wochentage,),
# "j": Jahreszeit}).
_WERKTAGE = (0, 1, 2, 3, 4)
_WOCHENENDE = (5, 6)


def _bauen(art, zeilen):
    ergebnis = []
    for zeile in zeilen:
        de, en = zeile[0], zeile[1]
        extra = zeile[2] if len(zeile) > 2 else {}
        ergebnis.append(
            {
                "art": art,
                "de": de,
                "en": en,
                "tageszeit": extra.get("t", "egal"),
                "wochentage": extra.get("w"),
                "jahreszeit": extra.get("j", "egal"),
            }
        )
    return ergebnis


# --- Lustige Familien- und Alltagssprüche -------------------------------------------------------

_SPRUECHE = [
    (
        "Socken sind wie Superhelden: Sie verschwinden und tauchen nie dort auf, wo man sie sucht.",
        "Socks are like superheroes: they vanish and never turn up where you look.",
    ),
    (
        "Die Spülmaschine ist nicht beleidigt, wenn du sie ausräumst. Sie freut sich sogar.",
        "The dishwasher won't be offended if you empty it. It might even be happy.",
    ),
    (
        "Eine Aufgabe pro Tag hält den Chaos-Drachen fern.",
        "One chore a day keeps the chaos dragon away.",
    ),
    (
        "Wer zuerst die Hand hebt, sichert sich die Punkte. Wer zweimal hinschaut, die Ruhe.",
        "First hand up gets the points. Second look gets some peace and quiet.",
    ),
    (
        "Punkte sammeln ist wie Treppensteigen: Stufe für Stufe, und plötzlich bist du oben.",
        "Collecting points is like climbing stairs: step by step, and suddenly you're at the top.",
    ),
    (
        "Der Müll geht nicht allein raus. Er hat es schon oft versucht.",
        "The trash won't take itself out. It has tried many times.",
    ),
    (
        "Ein aufgeräumtes Zimmer ist ein Zimmer, in dem man den Fußboden wiederentdeckt.",
        "A tidy room is one where you rediscover the floor.",
    ),
    (
        "Hausaufgaben sind wie Spinat: erst komisch, dann stark.",
        "Homework is like spinach: weird at first, then you feel strong.",
    ),
    (
        "Die Hausaufgaben laufen nicht weg. Aber sie warten sehr geduldig und sehr lange.",
        "Homework won't run away. It just waits very patiently, and for a very long time.",
    ),
    (
        "Heute schon was Nützliches getan? Der Stapel Wäsche meldet sich freiwillig.",
        "Done something useful today? The laundry pile is volunteering.",
    ),
    (
        "Ein Team ohne Aufgabenverteilung ist wie ein Fußballspiel mit fünf Bällen.",
        "A team without a chore plan is like a football match with five balls.",
    ),
    (
        "Ordnung ist das halbe Leben. Die andere Hälfte ist die Suche nach dem zweiten Schuh.",
        "Order is half of life. The other half is hunting for the second shoe.",
    ),
    (
        "Tisch decken: Gabel links, Messer rechts, gute Laune in die Mitte.",
        "Setting the table: fork left, knife right, good mood in the middle.",
    ),
    (
        "Wer den Tisch abräumt, ist der heimliche Held des Abendessens.",
        "Whoever clears the table is the secret hero of dinner.",
    ),
    (
        "Dreckige Teller sind nur Kunstwerke, die noch nicht fertig gespült sind.",
        "Dirty plates are just artworks that haven't been washed yet.",
    ),
    (
        "Das Bad glänzt, die Laune auch. Zufall? Wohl kaum.",
        "The bathroom sparkles, so does the mood. Coincidence? Hardly.",
    ),
    (
        "Fünf Minuten aufräumen sind schneller vorbei als eine Werbepause.",
        "Five minutes of tidying is over faster than a commercial break.",
    ),
    (
        "Wer klein anfängt, ist schneller fertig, als er denkt.",
        "Start small and you'll be done sooner than you think.",
    ),
    (
        "Staubsaugen ist Autorennen für Fortgeschrittene.",
        "Vacuuming is racing for advanced players.",
    ),
    (
        "Der Wäschekorb hat Hunger. Füttere ihn nur mit dem, was wirklich schmutzig ist.",
        "The laundry basket is hungry. Feed it only what is really dirty.",
    ),
    (
        "Wer Wäsche zusammenlegt, übt Origami mit Zukunft.",
        "Folding laundry is origami with a future.",
    ),
    (
        "Jeder Punkt zählt, sogar der, den man nicht sieht.",
        "Every point counts, even the one you can't see.",
    ),
    (
        "Wer heute den Müll rausbringt, wird morgen von den Mülltonnen gegrüßt.",
        "Whoever takes out the trash today gets waved at by the bins tomorrow.",
    ),
    (
        "Aufgaben sind wie Puzzleteile: Erst im Team ergeben sie ein schönes Bild.",
        "Chores are like puzzle pieces: only together do they make a nice picture.",
    ),
    (
        "Das Gemüse im Kühlschrank wartet auf einen Helden mit Schneidebrett.",
        "The veggies in the fridge are waiting for a hero with a chopping board.",
    ),
    (
        "Ein bisschen Chaos ist okay. Ein Berg Chaos braucht ein Team.",
        "A little mess is fine. A mountain of mess needs a team.",
    ),
    (
        "Erst die Pflicht, dann das Vergnügen – oder beides gleichzeitig mit Musik.",
        "Duty first, then fun - or both at once, with music.",
    ),
    (
        "Mit Musik wird jedes Abtrocknen zur Tanzstunde.",
        "With music, every bit of drying-up turns into a dance class.",
    ),
    (
        "Der Kleiderschrank ist kein Geheimversteck. Aber ein ziemlich gutes.",
        "The wardrobe is not a secret hideout. But it's a pretty good one.",
    ),
    (
        "Schultasche packen am Abend: Morgen-Ich sagt danke.",
        "Pack your school bag tonight: tomorrow-you says thank you.",
        {"t": "abend"},
    ),
    (
        "Das Frühstück ist der Anlauf für den Tag. Ohne Anlauf kein Sprung.",
        "Breakfast is the run-up for the day. No run-up, no jump.",
        {"t": "morgen"},
    ),
    (
        "Zähneputzen: zwei Minuten für ein Lächeln, das den ganzen Tag hält.",
        "Brushing teeth: two minutes for a smile that lasts all day.",
        {"t": "morgen"},
    ),
    (
        "Zähne geputzt, Pyjama an, Gedanken an morgen aus. Gute Reise ins Traumland.",
        "Teeth brushed, pyjamas on, thoughts about tomorrow off. Safe trip to dreamland.",
        {"t": "abend"},
    ),
    (
        "Das Kopfkissen ruft schon. Es hat heute besonders viel Federn für dich.",
        "Your pillow is already calling. It has extra fluff for you tonight.",
        {"t": "nacht"},
    ),
    (
        "Mittagessen: Der Magen schickt dem Gehirn einen Dankesbrief.",
        "Lunch: the tummy sends the brain a thank-you note.",
        {"t": "mittag"},
    ),
    (
        "Nach dem Essen noch schnell den Tisch abräumen, dann ist Ruhe im Karton.",
        "Quickly clear the table after eating and everything is peaceful.",
        {"t": "mittag"},
    ),
    (
        "Nachmittags ist die beste Zeit für eine Aufgabe, bevor der Sofa-Magnet zuschlägt.",
        "Afternoon is the best time for a chore, before the sofa magnet strikes.",
        {"t": "nachmittag"},
    ),
    (
        "Montag ist nur ein Dienstag, der sich zu früh angemeldet hat.",
        "Monday is just a Tuesday that signed up too early.",
        {"w": (0,)},
    ),
    (
        "Mittwoch: Berg-Mitte. Ab jetzt geht es bergab, Richtung Wochenende.",
        "Wednesday: the middle of the mountain. From here it's downhill to the weekend.",
        {"w": (2,)},
    ),
    (
        "Freitag: Die Woche packt schon ihren Koffer.",
        "Friday: the week is already packing its suitcase.",
        {"w": (4,)},
    ),
    (
        "Am Wochenende heißt das Zauberwort: Ausschlafen. Das zweite: Pfannkuchen.",
        "On weekends the magic word is sleeping in. The second one is pancakes.",
        {"w": _WOCHENENDE},
    ),
    (
        "Sonntag ist der Tag, an dem der Montag schon leise anklopft.",
        "Sunday is the day Monday starts knocking quietly.",
        {"w": (6,)},
    ),
    (
        "Samstags ist Familienzeit: Wer den Müll rausbringt, darf den Film aussuchen.",
        "Saturday is family time: whoever takes out the trash picks the movie.",
        {"w": (5,)},
    ),
    (
        "Im Sommer schmilzt das Eis schneller als die To-do-Liste.",
        "In summer, the ice cream melts faster than the to-do list.",
        {"j": "sommer"},
    ),
    (
        "Sommerhitze und Spülmaschine: beide laufen auf Hochtouren.",
        "Summer heat and the dishwasher: both are running at full speed.",
        {"j": "sommer"},
    ),
    (
        "Im Herbst gibt es viele Blätter. Und Gummistiefel mit Matsch-Garantie.",
        "Autumn brings lots of leaves, and boots with a mud guarantee.",
        {"j": "herbst"},
    ),
    (
        "Der Herbst hat Kürbisse im Angebot. Wer schnitzt mit?",
        "Autumn has pumpkins on offer. Who's carving?",
        {"j": "herbst"},
    ),
    (
        "Im Winter ist die Heizung der beste Freund und die Mütze der zweitbeste.",
        "In winter, the heater is your best friend and your hat is second best.",
        {"j": "winter"},
    ),
    (
        "Winterzeit ist Kakaozeit. Die Tassen spülen sich aber nicht von selbst.",
        "Winter is cocoa time. The mugs won't wash themselves, though.",
        {"j": "winter"},
    ),
    (
        "Im Frühling wachen sogar die Pflanzen auf. Du schaffst das auch!",
        "In spring even the plants wake up. You can do it too!",
        {"j": "fruehling"},
    ),
    (
        "Frühjahrsputz: Der Staub hat schon gepackt und winkt zum Abschied.",
        "Spring cleaning: the dust has packed its bags and is waving goodbye.",
        {"j": "fruehling"},
    ),
    (
        "Wenn alle mit anpacken, wird aus einem Berg Arbeit ein Hügel.",
        "When everyone pitches in, a mountain of work becomes a hill.",
    ),
    (
        "Eine Familie ist ein Orchester. Manchmal fehlt nur noch jemand mit Besen.",
        "A family is an orchestra. Sometimes you just need someone with a broom.",
    ),
    (
        "Achtung, Gefahr: Gleich wird gelacht und dabei vielleicht sogar aufgeräumt.",
        "Warning: laughter ahead, and possibly even some tidying.",
    ),
    (
        "Wer den Boden wischt, hinterlässt Spuren – glänzende.",
        "Whoever mops the floor leaves traces - shiny ones.",
    ),
    (
        "Ein leerer Geschirrspüler ist ein glücklicher Geschirrspüler.",
        "An empty dishwasher is a happy dishwasher.",
    ),
    (
        "Erst Teller, dann Tassen, dann die Gläser. Ordnung macht auch Spaß.",
        "Plates first, then cups, then glasses. Order can be fun too.",
    ),
    (
        "Der Papierkorb hat Hunger auf Zettel. Das Bett nicht.",
        "The wastepaper basket is hungry for scraps of paper. The bed isn't.",
    ),
    (
        "Das Bett machen dauert eine Minute. Danach fühlst du dich wie ein Hotelgast.",
        "Making your bed takes a minute. After that you feel like a hotel guest.",
        {"t": "morgen"},
    ),
    (
        "Schuhe ins Regal: So finden sie sich selbst, ohne Detektiv.",
        "Shoes onto the shelf: that way they find themselves, no detective needed.",
    ),
    (
        "Jacke an den Haken: So wird sie zum Star der Garderobe.",
        "Jacket on the hook: that's how it becomes the star of the coat rack.",
    ),
    (
        "Aus Chaos mach Kunst: Dazu gehört auch ein sauberer Schreibtisch.",
        "Turn chaos into art - a clean desk is part of it.",
    ),
    (
        "Frisch gelüftet ist halb gewonnen. Fenster auf und tief durchatmen.",
        "Fresh air is half the battle. Open the window and breathe deeply.",
    ),
    (
        "Wer den Rucksack ausleert, findet manchmal Schätze. Oder ein altes Pausenbrot.",
        "Empty your backpack and you may find treasure. Or an old sandwich.",
    ),
    (
        "Ein Pausenbrot, das zwei Wochen im Rucksack war, ist kein Brot mehr, sondern Forschung.",
        "A sandwich two weeks in the backpack is no longer lunch but science.",
    ),
    (
        "Heute ist ein guter Tag, um ein bisschen Superheld zu sein.",
        "Today is a good day to be a little bit of a superhero.",
    ),
    (
        "Die Zimmerpflanze hat Durst. Sie sagt es nur sehr leise.",
        "The houseplant is thirsty. It just says so very quietly.",
    ),
    ("Blumen gießen: Du bist der Regen von heute.", "Watering the flowers: you are today's rain."),
    (
        "Nicht die Größe der Aufgabe zählt, sondern der Schwung beim Anfangen.",
        "It's not the size of the chore that counts, but the swing you start with.",
    ),
    (
        "Mit drei Schritten ist jede Aufgabe machbar: anfangen, weitermachen, feiern.",
        "Any chore works in three steps: start, keep going, celebrate.",
    ),
    (
        "Die Fernbedienung ist kein Staubwedel, auch wenn sie oft zum Einsatz kommt.",
        "The remote control is not a duster, even if it often ends up as one.",
    ),
    (
        "Ohne Bücherregal-Ordnung sind Bücher nur Papier-Dominos.",
        "Without a tidy bookshelf, books are just paper dominoes.",
    ),
    (
        "Wer die Zeit stoppt, merkt: Aufräumen dauert kürzer als Diskutieren.",
        "Time it, and you'll see: tidying takes less time than arguing about it.",
    ),
    (
        "Das Familienziel ist wie ein Lagerfeuer: Je mehr Holz, desto wärmer.",
        "The family goal is like a campfire: the more wood, the warmer it gets.",
    ),
    ("Alle für einen, einer für die Spülmaschine.", "All for one, and one for the dishwasher."),
    (
        "Wer mit anpackt, hat hinterher das beste Gefühl und manchmal ein Eis.",
        "Whoever pitches in gets the best feeling afterwards, and sometimes an ice cream.",
    ),
    (
        "Küchenregel Nummer eins: Wer kocht, muss nicht spülen. Wer spült, muss nicht kochen.",
        "Kitchen rule number one: the cook doesn't wash up, and the washer doesn't cook.",
    ),
    (
        "Kartoffeln schälen ist Entspannung mit Ergebnis.",
        "Peeling potatoes is relaxation with a result.",
    ),
    (
        "Der Kühlschrank leuchtet, wenn er geöffnet wird. Er ist also heimlich eine Lampe.",
        "The fridge lights up when it's opened. So it's secretly a lamp.",
    ),
    (
        "Das Licht im Flur macht keinen Urlaub. Bitte ausschalten, wenn du gehst.",
        "The hallway light isn't on holiday. Please switch it off when you leave.",
    ),
    (
        "Wasser sparen beim Zähneputzen: Der Hahn macht gern mal Pause.",
        "Save water while brushing your teeth: the tap likes a break.",
    ),
    (
        "Mülltrennung ist ein Spiel: Papier, Plastik, Bio. Wer hat die meisten Treffer?",
        "Sorting trash is a game: paper, plastic, organic. Who scores the most?",
    ),
    (
        "Altpapier ist die Zeitreise der Zeitung: erst lesen, dann recyceln.",
        "Old paper is a newspaper's time travel: first read, then recycled.",
    ),
    (
        "Das Pfandflaschen-Regal staunt: So viel Teamarbeit auf einmal!",
        "The bottle-deposit crate is amazed: so much teamwork at once!",
    ),
    (
        "Hausaufgaben zuerst, dann gibt es ein ruhiges Gewissen gratis dazu.",
        "Homework first, then you get a clear conscience for free.",
        {"t": "nachmittag"},
    ),
    (
        "Lesen ist Kino im Kopf. Eintritt frei, Popcorn optional.",
        "Reading is cinema in your head. Free entry, popcorn optional.",
    ),
    (
        "Mathe ist Detektivarbeit mit Zahlen. Jede Lösung ist ein Fall weniger.",
        "Maths is detective work with numbers. Every solution is one case closed.",
    ),
    (
        "Ein Fehler beim Lernen ist ein Hinweisschild, kein Stoppschild.",
        "A mistake while learning is a signpost, not a stop sign.",
    ),
    (
        "Vokabeln sind wie Gummibärchen: Wer täglich ein paar nascht, hat bald viele.",
        "Vocabulary is like gummy bears: have a few every day and soon you've got loads.",
    ),
    (
        "Wer viel lernt, hat abends ein müdes Gehirn und ein zufriedenes Grinsen.",
        "Learn a lot and you end the day with a tired brain and a happy grin.",
        {"t": "abend"},
    ),
    (
        "Wir sind ein Team: Gemeinsam sind wir unschlagbar im Aufräumen.",
        "We are a team: together we're unbeatable at tidying up.",
    ),
    (
        "Wenn der Wecker klingelt, ist das nur die Einladung zu einem neuen Abenteuer.",
        "When the alarm rings, it's just an invitation to a new adventure.",
        {"t": "morgen"},
    ),
    (
        "Die Morgenmuffel-Regel: Erst anziehen, dann meckern. Meistens reicht das erste.",
        "The grumpy-morning rule: get dressed first, grumble later. Often the first is enough.",
        {"t": "morgen", "w": _WERKTAGE},
    ),
    (
        "Pausenbrot eingepackt? Dann kann der Schultag kommen.",
        "Lunchbox packed? Then the school day can come.",
        {"t": "morgen", "w": _WERKTAGE},
    ),
    (
        "Die Schuhe passen nur dann nicht, wenn du sie an den falschen Fuß ziehst.",
        "Shoes only don't fit when you put them on the wrong feet.",
    ),
    (
        "Müde Beine, aber volle Punkte: So sieht ein guter Tag aus.",
        "Tired legs but full points: that's what a good day looks like.",
        {"t": "abend"},
    ),
    (
        "Der Tag war lang, die Familie war toll. Das reicht für ein Gute-Nacht-Lächeln.",
        "The day was long and the family was great. That's enough for a goodnight smile.",
        {"t": "nacht"},
    ),
    (
        "Pssst, die Zahnfee kontrolliert heute nur die Zähne, die geputzt sind.",
        "Psst, the tooth fairy only checks teeth that have been brushed tonight.",
        {"t": "nacht"},
    ),
    (
        "Beim Abendbrot gilt: Alle Gabeln nach vorn, alle Handys nach hinten.",
        "At dinner the rule is: all forks forward, all phones back.",
        {"t": "abend"},
    ),
    (
        "Ein Quäntchen Humor macht jede Aufgabe leichter.",
        "A pinch of humour makes any chore lighter.",
    ),
    (
        "Nicht meckern, sondern machen – und danach eine kleine Siegerpose.",
        "Don't grumble, just do it - and then strike a little winner's pose.",
    ),
    (
        "Wer zuhört, wenn jemand etwas erklärt, spart sich später die Wiederholung.",
        "Listen when someone explains something and you'll skip the repeat later.",
    ),
    (
        "Kein Streit ums Aufräumen: Ein Wettlauf mit der Küchenuhr löst alles.",
        "No arguments about tidying: a race against the kitchen timer settles everything.",
    ),
    (
        "Wer die Küche aufräumt, hat auch das Recht auf den ersten Löffel Nachtisch.",
        "Whoever tidies the kitchen has the right to the first spoon of dessert.",
        {"t": "abend"},
    ),
    (
        "Was lange liegt, wird endlich weggeräumt. Heute vielleicht?",
        "What's been lying around for ages finally gets put away. Maybe today?",
    ),
    (
        "Lachen ist ansteckend. Gib es gern weiter!",
        "Laughter is contagious. Pass it on!",
    ),
    (
        "Der Teppich hat sich beschwert: zu viele Krümel, zu wenig Staubsauger.",
        "The carpet complained: too many crumbs, not enough vacuum cleaner.",
    ),
]

# --- Kindgerechte Weisheiten und Mut-Sprüche ------------------------------------------------------

_WEISHEITEN = [
    (
        "Aller Anfang ist schwer – aber jeder Anfang ist auch ein Anfang.",
        "Every beginning is hard - but every beginning is still a beginning.",
    ),
    ("Übung macht den Meister.", "Practice makes perfect."),
    ("Wer nicht wagt, der nicht gewinnt.", "Nothing ventured, nothing gained."),
    ("Kleine Schritte führen auch ans Ziel.", "Small steps get you there too."),
    (
        "Fehler sind erlaubt. Wer nichts probiert, lernt auch nichts.",
        "Mistakes are allowed. If you never try, you never learn.",
    ),
    (
        "Du musst nicht perfekt sein, um etwas Gutes zu tun.",
        "You don't have to be perfect to do something good.",
    ),
    (
        "Mut heißt nicht, keine Angst zu haben, sondern es trotzdem zu probieren.",
        "Courage doesn't mean having no fear. It means trying anyway.",
    ),
    ("Jeder Tag ist eine neue Chance.", "Every day is a new chance."),
    ("Gemeinsam sind wir stark.", "Together we are strong."),
    ("Wer anderen hilft, hilft auch sich selbst.", "Helping others also helps yourself."),
    (
        "Ein freundliches Wort kostet nichts und wärmt lange.",
        "A kind word costs nothing and warms for a long time.",
    ),
    ("Geteilte Freude ist doppelte Freude.", "A joy shared is a joy doubled."),
    (
        "Geduld ist die Kunst, zu warten, ohne schlechte Laune zu bekommen.",
        "Patience is the art of waiting without getting grumpy.",
    ),
    ("Steter Tropfen höhlt den Stein.", "Constant dripping wears away the stone."),
    (
        "Was du heute kannst besorgen, das verschiebe nicht auf morgen.",
        "Never put off until tomorrow what you can do today.",
    ),
    ("Probieren geht über Studieren.", "The proof of the pudding is in the eating."),
    ("Neugier ist der Anfang von allem Wissen.", "Curiosity is where all knowledge begins."),
    ("Wer fragt, bleibt nicht dumm.", "Whoever asks doesn't stay clueless."),
    (
        "Frag ruhig nach. Es gibt keine dummen Fragen, nur noch nicht gestellte.",
        "Go ahead and ask. There are no silly questions, only ones not yet asked.",
    ),
    (
        "Wenn etwas nicht klappt, probier einen anderen Weg.",
        "If something doesn't work, try another way.",
    ),
    (
        "Auch der längste Weg beginnt mit dem ersten Schritt.",
        "Even the longest journey begins with a single step.",
    ),
    ("Glück ist, wenn man trotzdem lacht.", "Happiness is laughing anyway."),
    ("Ehrlich währt am längsten.", "Honesty is the best policy."),
    ("Wer zuhört, versteht mehr.", "Whoever listens understands more."),
    (
        "Jeder ist in etwas gut. Finde heraus, worin du es bist.",
        "Everyone is good at something. Find out what yours is.",
    ),
    (
        "Anders sein ist keine Schwäche, sondern deine Superkraft.",
        "Being different isn't a weakness, it's your superpower.",
    ),
    (
        "Niemand weiß alles. Zusammen wissen wir ganz schön viel.",
        "Nobody knows everything. Together we know quite a lot.",
    ),
    (
        "Es ist okay, um Hilfe zu bitten. Das ist mutig.",
        "It's okay to ask for help. That takes courage.",
    ),
    (
        "Trau dich! Das Schlimmste ist meistens nur ein Schritt.",
        "Go for it! The scariest part is usually just one step.",
    ),
    (
        "Wer weitermacht, hat schon halb gewonnen.",
        "Keep going and you're already halfway there.",
    ),
    ("Heute gelernt, morgen gekonnt.", "Learned today, can do tomorrow."),
    (
        "Schau nicht, wie weit es noch ist, sondern wie weit du schon gekommen bist.",
        "Don't look at how far is left, look at how far you've come.",
    ),
    ("Mit Freundlichkeit kommt man überall durch die Tür.", "Kindness opens every door."),
    (
        "Lächeln ist die kürzeste Verbindung zwischen zwei Menschen.",
        "A smile is the shortest link between two people.",
    ),
    (
        "Jeder fängt mal klein an. Auch der größte Baum war einmal ein Samenkorn.",
        "Everyone starts small. Even the tallest tree was once a seed.",
    ),
    (
        "Wer sich Mühe gibt, darf stolz sein, egal wie es ausgeht.",
        "If you gave it your best, you can be proud, however it turns out.",
    ),
    (
        "Heute ist ein guter Tag, um etwas Neues zu lernen.",
        "Today is a good day to learn something new.",
    ),
    (
        "Dein Gehirn ist wie ein Muskel: Je mehr du übst, desto stärker wird es.",
        "Your brain is like a muscle: the more you practise, the stronger it gets.",
    ),
    ("Wer langsam geht, kommt auch an.", "Slow and steady wins the race."),
    ("In der Ruhe liegt die Kraft.", "In calm there is strength."),
    ("Nach Regen kommt Sonnenschein.", "After rain comes sunshine."),
    ("Ein Lachen am Tag macht das Herz leicht.", "A laugh a day keeps the heart light."),
    ("Jede Reise ist leichter mit guter Gesellschaft.", "Every journey is easier in good company."),
    ("Wer teilt, hat mehr vom Leben.", "Those who share get more out of life."),
    (
        "Selbst die kleinste Hilfe ist groß, wenn sie von Herzen kommt.",
        "Even the smallest help is big when it comes from the heart.",
    ),
    ("Du bist wichtig, genau so, wie du bist.", "You matter, exactly as you are."),
    (
        "Wer Fehler macht, ist mutig genug zu probieren.",
        "Making mistakes means you were brave enough to try.",
    ),
    (
        "Nicht alles klappt gleich beim ersten Mal. Beim zehnten oft schon.",
        "Not everything works the first time. Often it does by the tenth.",
    ),
    ("Atme tief durch. Eins nach dem anderen.", "Take a deep breath. One thing at a time."),
    ("Ein guter Plan ist ein halber Erfolg.", "A good plan is half the success."),
    (
        "Wenn du etwas wirklich willst, finde einen Weg, kein Hindernis.",
        "If you really want something, look for a way, not for an obstacle.",
    ),
    ("Aus kleinen Bausteinen entstehen große Burgen.", "Big castles are built from small blocks."),
    (
        "Wer sich zuerst entschuldigt, ist der Größere.",
        "Whoever says sorry first is the bigger one.",
    ),
    (
        "Sag danke, auch für Kleinigkeiten. Das macht beide froh.",
        "Say thank you, even for little things. It makes both of you happy.",
    ),
    ("Teamgeist schlägt Einzelkämpfer.", "Team spirit beats going solo."),
    ("Der beste Zeitpunkt anzufangen ist jetzt.", "The best time to start is now."),
    (
        "Jeder Tag hat zwei Henkel: Greif den, der dich froh macht.",
        "Every day has two handles: pick the one that makes you glad.",
    ),
    ("Es ist nie zu spät, etwas zu lernen.", "It's never too late to learn something."),
    (
        "Heute zählt: eine gute Tat, ein Lächeln, ein Versuch.",
        "Today counts: one good deed, one smile, one try.",
    ),
    (
        "Lass dich von einem Misserfolg nicht stoppen, lern daraus.",
        "Don't let a failure stop you, learn from it.",
    ),
    ("Wer träumt, kann auch loslaufen.", "Whoever dreams can also start walking."),
    (
        "Ruhe hilft dem Kopf, auf neue Ideen zu kommen.",
        "Rest helps your head come up with new ideas.",
        {"t": "abend"},
    ),
    (
        "Gut geschlafen ist halb gelernt.",
        "A good night's sleep is half the learning.",
        {"t": "abend"},
    ),
    ("Der Morgen bringt Rat.", "Sleep on it: the morning brings advice.", {"t": "morgen"}),
    (
        "Wer früh anfängt, hat mehr vom Tag.",
        "Start early and you get more of the day.",
        {"t": "morgen"},
    ),
    ("Der frühe Vogel fängt den Wurm.", "The early bird catches the worm.", {"t": "morgen"}),
    (
        "Nach dem Essen sollst du ruhn oder tausend Schritte tun.",
        "After a meal, sit a while or walk a mile.",
        {"t": "mittag"},
    ),
    (
        "Ein kleiner Spaziergang macht den Kopf frei.",
        "A little walk clears your head.",
        {"t": "nachmittag"},
    ),
    (
        "Auch ein langer Tag geht zu Ende. Du hast viel geschafft.",
        "Even a long day comes to an end. You did a lot.",
        {"t": "abend"},
    ),
    (
        "Träume süß: Morgen wartet ein neuer Tag voller Möglichkeiten.",
        "Sweet dreams: tomorrow is a new day full of possibilities.",
        {"t": "nacht"},
    ),
    (
        "Der Mond ist nachts nie allein, er hat die Sterne.",
        "The moon is never alone at night, it has the stars.",
        {"t": "nacht"},
    ),
    (
        "Im Frühling beginnt alles neu. Das gilt auch für gute Vorsätze.",
        "In spring everything starts anew. That goes for good resolutions too.",
        {"j": "fruehling"},
    ),
    (
        "Was im Frühling gesät wird, wächst im Sommer. Das gilt auch fürs Lernen.",
        "What's sown in spring grows in summer. Same goes for learning.",
        {"j": "fruehling"},
    ),
    (
        "Der Sommer ist da, um Kraft zu tanken. Tank mit!",
        "Summer is here to recharge. Join in!",
        {"j": "sommer"},
    ),
    (
        "Im Herbst ernten wir, was wir gesät haben. Auch beim Lernen.",
        "In autumn we harvest what we've sown. In learning too.",
        {"j": "herbst"},
    ),
    (
        "Im Winter wachsen die Wurzeln im Stillen, bis es wieder grünt.",
        "In winter roots grow quietly until it turns green again.",
        {"j": "winter"},
    ),
    (
        "Montag ist ein guter Tag für einen frischen Start.",
        "Monday is a good day for a fresh start.",
        {"w": (0,)},
    ),
    (
        "Es ist Freitag: Ihr habt euch das Wochenende verdient.",
        "It's Friday: you've earned your weekend.",
        {"w": (4,)},
    ),
    (
        "Ein freier Tag ist wie ein leeres Blatt Papier. Was malst du?",
        "A day off is like a blank sheet of paper. What will you draw?",
        {"w": _WOCHENENDE},
    ),
    ("Wer viel liest, reist ohne Koffer.", "Reading a lot is travelling without luggage."),
    (
        "Wer pünktlich ist, schenkt anderen Zeit.",
        "Being on time gives other people the gift of time.",
    ),
    (
        "Ein Versprechen ist wie eine Brücke: Halte es, damit andere darübergehen können.",
        "A promise is like a bridge: keep it so others can cross.",
    ),
    ("Wähle die Worte so, dass sie jemanden aufbauen.", "Choose words that lift someone up."),
    (
        "Sei freundlich, denn jeder kämpft mal mit etwas Schwierigem.",
        "Be kind, because everyone sometimes struggles with something hard.",
    ),
    (
        "Wer Pflichten erfüllt, hat den Kopf frei für Spaß.",
        "Do your duties and your head is free for fun.",
    ),
    (
        "Zusammen schafft man in einer Stunde, was einer in drei Stunden nicht schafft.",
        "Together you do in an hour what one person can't in three.",
    ),
]

# --- „Wusstest du?“-Fakten (nur gut gesicherte, allgemein bekannte) -------------------------------

_FAKTEN = [
    # Tiere
    ("Wusstest du? Ein Oktopus hat drei Herzen.", "Did you know? An octopus has three hearts."),
    (
        "Wusstest du? Schmetterlinge schmecken mit den Füßen.",
        "Did you know? Butterflies taste with their feet.",
    ),
    (
        "Wusstest du? Fast alle Säugetiere haben sieben Halswirbel, Giraffe und Mensch auch.",
        "Did you know? Almost all mammals have seven neck bones, giraffes and humans too.",
    ),
    (
        "Wusstest du? Delfine schlafen mit nur einer Gehirnhälfte, die andere bleibt wach.",
        "Did you know? Dolphins sleep with half their brain, the other half stays awake.",
    ),
    (
        "Wusstest du? Der Gepard ist das schnellste Landtier.",
        "Did you know? The cheetah is the fastest land animal.",
    ),
    (
        "Wusstest du? Wale sind keine Fische, sondern Säugetiere.",
        "Did you know? Whales aren't fish, they are mammals.",
    ),
    (
        "Wusstest du? Der Blauwal ist das größte Tier, das jemals gelebt hat.",
        "Did you know? The blue whale is the biggest animal that ever lived.",
    ),
    (
        "Wusstest du? Bei Seepferdchen tragen die Männchen die Jungen aus.",
        "Did you know? Among seahorses, the males carry the babies.",
    ),
    (
        "Wusstest du? Fledermäuse sind die einzigen Säugetiere, die richtig fliegen können.",
        "Did you know? Bats are the only mammals that can truly fly.",
    ),
    (
        "Wusstest du? Kolibris können sogar rückwärts fliegen.",
        "Did you know? Hummingbirds can even fly backwards.",
    ),
    (
        "Wusstest du? Spinnen sind keine Insekten. Sie haben acht Beine, Insekten sechs.",
        "Did you know? Spiders aren't insects. They have eight legs, insects have six.",
    ),
    (
        "Wusstest du? Kaiserpinguin-Papas wärmen das Ei auf ihren Füßen.",
        "Did you know? Emperor penguin dads keep the egg warm on their feet.",
    ),
    (
        "Wusstest du? Bienen zeigen sich mit einem Tanz, wo es Blüten gibt.",
        "Did you know? Bees use a dance to show each other where the flowers are.",
    ),
    (
        "Wusstest du? Ein Chamäleon kann seine Augen unabhängig voneinander bewegen.",
        "Did you know? A chameleon can move its eyes independently of each other.",
    ),
    (
        "Wusstest du? Seeotter halten im Schlaf Pfoten, damit sie nicht auseinandertreiben.",
        "Did you know? Sea otters hold paws while sleeping so they don't drift apart.",
    ),
    (
        "Wusstest du? Wombats machen würfelförmige Köttel.",
        "Did you know? Wombat droppings are shaped like little cubes.",
    ),
    (
        "Wusstest du? Flamingos werden durch ihr Futter rosa.",
        "Did you know? Flamingos turn pink because of the food they eat.",
    ),
    (
        "Wusstest du? Ein Zebra hat ein ganz eigenes Streifenmuster, wie ein Fingerabdruck.",
        "Did you know? Every zebra has its own stripe pattern, like a fingerprint.",
    ),
    (
        "Wusstest du? Der Strauß ist der größte Vogel der Welt. Fliegen kann er nicht.",
        "Did you know? The ostrich is the world's biggest bird. It can't fly.",
    ),
    (
        "Wusstest du? Elefanten sind die größten Landtiere der Erde.",
        "Did you know? Elephants are the biggest land animals on Earth.",
    ),
    (
        "Wusstest du? Kamele speichern in ihrem Höcker Fett, nicht Wasser.",
        "Did you know? Camels store fat in their humps, not water.",
    ),
    (
        "Wusstest du? Die Haut eines Eisbären ist schwarz.",
        "Did you know? A polar bear's skin is black.",
    ),
    (
        "Wusstest du? Ameisen können ein Vielfaches ihres eigenen Gewichts tragen.",
        "Did you know? Ants can carry many times their own weight.",
    ),
    (
        "Wusstest du? Glühwürmchen leuchten durch eine chemische Reaktion in ihrem Körper.",
        "Did you know? Fireflies glow thanks to a chemical reaction in their bodies.",
    ),
    ("Wusstest du? Seesterne haben kein Gehirn.", "Did you know? Starfish don't have a brain."),
    (
        "Wusstest du? Schnecken haben tausende winzige Zähne auf der Zunge.",
        "Did you know? Snails have thousands of tiny teeth on their tongue.",
    ),
    (
        "Wusstest du? Biber haben Zähne, die ein Leben lang nachwachsen.",
        "Did you know? A beaver's teeth keep growing for its whole life.",
    ),
    (
        "Wusstest du? Haie gab es schon, bevor es Bäume gab.",
        "Did you know? Sharks were around before there were trees.",
    ),
    (
        "Wusstest du? Die Vorfahren der Libellen flogen schon vor den Dinosauriern.",
        "Did you know? The ancestors of dragonflies flew before the dinosaurs.",
    ),
    (
        "Wusstest du? Papageien können Wörter nachsprechen.",
        "Did you know? Parrots can copy human words.",
    ),
    ("Wusstest du? Ein Oktopus hat blaues Blut.", "Did you know? An octopus has blue blood."),
    (
        "Wusstest du? Raupen verwandeln sich in der Puppe in Schmetterlinge.",
        "Did you know? Caterpillars turn into butterflies inside the chrysalis.",
    ),
    (
        "Wusstest du? Zugvögel fliegen im Herbst oft tausende Kilometer in den Süden.",
        "Did you know? In autumn, migrating birds often fly thousands of kilometres south.",
        {"j": "herbst"},
    ),
    (
        "Wusstest du? Koalas schlafen den größten Teil des Tages.",
        "Did you know? Koalas sleep for most of the day.",
    ),
    (
        "Wusstest du? Die Eule kann ihren Kopf viel weiter drehen als wir.",
        "Did you know? An owl can turn its head much further than we can.",
    ),
    (
        "Wusstest du? Lachse schwimmen zum Laichen zurück in ihren Heimatfluss.",
        "Did you know? Salmon swim back to their home river to spawn.",
    ),
    (
        "Wusstest du? Ein Igel hält im Winter Winterschlaf.",
        "Did you know? Hedgehogs hibernate in winter.",
        {"j": "winter"},
    ),
    (
        "Wusstest du? Honig verdirbt fast nie, wenn man ihn gut verschließt.",
        "Did you know? Honey almost never spoils if you keep it sealed.",
    ),
    # Weltall
    (
        "Wusstest du? Die Erde dreht sich einmal am Tag um sich selbst.",
        "Did you know? The Earth spins around itself once a day.",
    ),
    (
        "Wusstest du? Der Mond leuchtet nicht selbst, er spiegelt das Licht der Sonne.",
        "Did you know? The Moon doesn't shine by itself, it reflects sunlight.",
    ),
    ("Wusstest du? Die Sonne ist ein Stern.", "Did you know? The Sun is a star."),
    (
        "Wusstest du? In die Sonne würden mehr als eine Million Erden passen.",
        "Did you know? More than a million Earths would fit inside the Sun.",
    ),
    (
        "Wusstest du? Das Sonnenlicht braucht rund acht Minuten bis zu uns.",
        "Did you know? Sunlight takes about eight minutes to reach us.",
    ),
    (
        "Wusstest du? Der Mond entfernt sich jedes Jahr ein paar Zentimeter von der Erde.",
        "Did you know? The Moon drifts a few centimetres further from Earth every year.",
    ),
    (
        "Wusstest du? Die Venus ist der heißeste Planet unseres Sonnensystems.",
        "Did you know? Venus is the hottest planet in our solar system.",
    ),
    (
        "Wusstest du? Jupiter ist der größte Planet in unserem Sonnensystem.",
        "Did you know? Jupiter is the biggest planet in our solar system.",
    ),
    (
        "Wusstest du? Die Ringe des Saturn bestehen aus Eis- und Gesteinsbrocken.",
        "Did you know? Saturn's rings are made of chunks of ice and rock.",
    ),
    (
        "Wusstest du? Der Mars ist rot, weil sein Staub Rost enthält.",
        "Did you know? Mars is red because its dust contains rust.",
    ),
    (
        "Wusstest du? Auf der Venus dauert ein Tag länger als ein Jahr.",
        "Did you know? On Venus, one day lasts longer than one year.",
    ),
    (
        "Wusstest du? Im Weltall hört man nichts, weil es dort keine Luft gibt.",
        "Did you know? In space you can't hear anything because there is no air.",
    ),
    (
        "Wusstest du? Pluto ist seit 2006 ein Zwergplanet.",
        "Did you know? Pluto has been a dwarf planet since 2006.",
    ),
    (
        "Wusstest du? Merkur ist der kleinste Planet in unserem Sonnensystem.",
        "Did you know? Mercury is the smallest planet in our solar system.",
    ),
    (
        "Wusstest du? Uranus rollt fast auf der Seite um die Sonne.",
        "Did you know? Uranus travels around the Sun almost lying on its side.",
    ),
    (
        "Wusstest du? Unsere Milchstraße hat Hunderte Milliarden Sterne.",
        "Did you know? Our Milky Way has hundreds of billions of stars.",
    ),
    (
        "Wusstest du? Sternschnuppen sind keine Sterne, sondern kleine glühende Steinchen.",
        "Did you know? Shooting stars aren't stars, just tiny glowing bits of rock.",
    ),
    (
        "Wusstest du? Juri Gagarin war 1961 der erste Mensch im Weltall.",
        "Did you know? Yuri Gagarin became the first human in space in 1961.",
    ),
    (
        "Wusstest du? 1969 landeten die ersten Menschen auf dem Mond.",
        "Did you know? The first humans landed on the Moon in 1969.",
    ),
    (
        "Wusstest du? Auf dem Mond ist die Schwerkraft viel kleiner. Man könnte hoch hüpfen.",
        "Did you know? Gravity on the Moon is much weaker. You could jump really high.",
    ),
    (
        "Wusstest du? Der Schweif eines Kometen zeigt immer von der Sonne weg.",
        "Did you know? A comet's tail always points away from the Sun.",
    ),
    (
        "Wusstest du? Astronauten werden im Weltall vorübergehend ein paar Zentimeter größer.",
        "Did you know? Astronauts grow a few centimetres taller in space, but only for a while.",
    ),
    (
        "Wusstest du? Die Raumstation ISS umkreist die Erde mehrmals am Tag.",
        "Did you know? The ISS space station circles the Earth several times a day.",
    ),
    (
        "Wusstest du? Ebbe und Flut entstehen vor allem durch die Anziehung des Mondes.",
        "Did you know? Tides are mainly caused by the Moon's pull.",
    ),
    (
        "Wusstest du? Die Erde braucht ein Jahr, um einmal um die Sonne zu laufen.",
        "Did you know? It takes Earth one year to travel once around the Sun.",
    ),
    (
        "Wusstest du? Neptun ist der am weitesten entfernte Planet der Sonne.",
        "Did you know? Neptune is the planet furthest from the Sun.",
    ),
    # Körper
    (
        "Wusstest du? Dein Herz schlägt Tag und Nacht, ohne je Pause zu machen.",
        "Did you know? Your heart beats day and night without ever taking a break.",
    ),
    (
        "Wusstest du? Erwachsene haben 206 Knochen. Babys haben noch mehr.",
        "Did you know? Adults have 206 bones. Babies have even more.",
    ),
    (
        "Wusstest du? Der Oberschenkelknochen ist der längste Knochen im Körper.",
        "Did you know? The thigh bone is the longest bone in the body.",
    ),
    (
        "Wusstest du? Die Haut ist das größte Organ des Menschen.",
        "Did you know? Skin is the largest organ of the human body.",
    ),
    (
        "Wusstest du? Sogar eineiige Zwillinge haben verschiedene Fingerabdrücke.",
        "Did you know? Even identical twins have different fingerprints.",
    ),
    (
        "Wusstest du? Der Zahnschmelz ist das härteste Material in deinem Körper.",
        "Did you know? Tooth enamel is the hardest material in your body.",
    ),
    ("Wusstest du? Kinder haben 20 Milchzähne.", "Did you know? Children have 20 baby teeth."),
    (
        "Wusstest du? Mehr als die Hälfte deines Körpers besteht aus Wasser.",
        "Did you know? More than half of your body is water.",
    ),
    (
        "Wusstest du? Die kleinsten Knochen des Körpers sitzen in deinem Ohr.",
        "Did you know? The smallest bones in your body are inside your ear.",
    ),
    (
        "Wusstest du? Im Schlaf hilft dein Gehirn dir, Gelerntes zu behalten.",
        "Did you know? While you sleep, your brain helps you remember what you've learned.",
        {"t": "abend"},
    ),
    (
        "Wusstest du? Rote Blutkörperchen bringen Sauerstoff durch den ganzen Körper.",
        "Did you know? Red blood cells carry oxygen around your whole body.",
    ),
    (
        "Wusstest du? Der größte Muskel im Körper ist der Gesäßmuskel.",
        "Did you know? The biggest muscle in the body is the buttock muscle.",
    ),
    (
        "Wusstest du? Dein Gehirn verbraucht viel Energie, auch wenn du nur still sitzt.",
        "Did you know? Your brain uses lots of energy even when you're just sitting still.",
    ),
    (
        "Wusstest du? Gähnen steckt an. Gähnst du jetzt auch?",
        "Did you know? Yawning is contagious. Are you yawning too?",
    ),
    (
        "Wusstest du? Dein Körper erneuert ständig deine Haut.",
        "Did you know? Your body constantly renews your skin.",
    ),
    # Natur
    (
        "Wusstest du? Pflanzen nehmen Kohlendioxid auf und geben Sauerstoff ab.",
        "Did you know? Plants take in carbon dioxide and give out oxygen.",
    ),
    (
        "Wusstest du? Ein Regenbogen entsteht, wenn Sonnenlicht auf Regentropfen trifft.",
        "Did you know? A rainbow appears when sunlight hits raindrops.",
    ),
    (
        "Wusstest du? Ein Blitz ist heißer als die Oberfläche der Sonne.",
        "Did you know? Lightning is hotter than the surface of the Sun.",
    ),
    (
        "Wusstest du? Schneekristalle haben immer eine sechseckige Grundform.",
        "Did you know? Snow crystals always have a six-sided basic shape.",
        {"j": "winter"},
    ),
    (
        "Wusstest du? Etwa 70 Prozent der Erdoberfläche sind mit Wasser bedeckt.",
        "Did you know? About 70 percent of the Earth's surface is covered by water.",
    ),
    (
        "Wusstest du? Der Mount Everest ist der höchste Berg der Erde.",
        "Did you know? Mount Everest is the highest mountain on Earth.",
    ),
    (
        "Wusstest du? Die Sahara ist die größte Heißwüste der Welt.",
        "Did you know? The Sahara is the largest hot desert in the world.",
    ),
    (
        "Wusstest du? Der Pazifik ist der größte Ozean der Erde.",
        "Did you know? The Pacific is the biggest ocean on Earth.",
    ),
    (
        "Wusstest du? Bambus gehört zu den am schnellsten wachsenden Pflanzen.",
        "Did you know? Bamboo is one of the fastest-growing plants.",
    ),
    (
        "Wusstest du? Junge Sonnenblumen drehen sich mit der Sonne mit.",
        "Did you know? Young sunflowers turn to follow the Sun.",
        {"j": "sommer"},
    ),
    (
        "Wusstest du? Botanisch sind Bananen Beeren, Erdbeeren aber nicht.",
        "Did you know? Botanically, bananas are berries but strawberries aren't.",
    ),
    (
        "Wusstest du? Pilze sind weder Pflanzen noch Tiere, sie sind ein eigenes Reich.",
        "Did you know? Mushrooms are neither plants nor animals, they have a kingdom of their own.",
    ),
    (
        "Wusstest du? Mammutbäume gehören zu den höchsten Bäumen der Welt.",
        "Did you know? Redwoods are among the tallest trees in the world.",
    ),
    (
        "Wusstest du? Die Antarktis ist der kälteste Kontinent der Erde.",
        "Did you know? Antarctica is the coldest continent on Earth.",
    ),
    (
        "Wusstest du? Tropfsteine in Höhlen wachsen nur sehr langsam.",
        "Did you know? Stalactites in caves grow very slowly.",
    ),
    (
        "Wusstest du? Ein Kürbis ist botanisch gesehen eine Beere.",
        "Did you know? Botanically speaking, a pumpkin is a berry.",
        {"j": "herbst"},
    ),
    (
        "Wusstest du? Im Frühling kehren viele Zugvögel zu uns zurück.",
        "Did you know? In spring, many migrating birds return to us.",
        {"j": "fruehling"},
    ),
    (
        "Wusstest du? Der Wasserkreislauf: Wasser verdunstet, wird Wolke und regnet wieder ab.",
        "Did you know? The water cycle: water evaporates, forms clouds and rains down again.",
    ),
    (
        "Wusstest du? Beim Gewitter siehst du den Blitz vor dem Donner, weil Licht schneller ist.",
        "Did you know? In a storm you see lightning before thunder because light is faster.",
    ),
    # Geschichte
    (
        "Wusstest du? Die Pyramiden von Gizeh sind mehr als 4000 Jahre alt.",
        "Did you know? The pyramids of Giza are more than 4,000 years old.",
    ),
    (
        "Wusstest du? Die großen Dinosaurier starben vor etwa 66 Millionen Jahren aus.",
        "Did you know? The big dinosaurs died out about 66 million years ago.",
    ),
    (
        "Wusstest du? Ein Tag auf dem Mars ist nur etwas länger als ein Tag auf der Erde.",
        "Did you know? A day on Mars is only slightly longer than a day on Earth.",
    ),
    (
        "Wusstest du? Gutenberg erfand in Europa den Buchdruck mit beweglichen Metallbuchstaben.",
        "Did you know? Gutenberg invented printing with movable metal type in Europe.",
    ),
    (
        "Wusstest du? Die Chinesische Mauer ist mehrere tausend Kilometer lang.",
        "Did you know? The Great Wall of China is several thousand kilometres long.",
    ),
    (
        "Wusstest du? Die Olympischen Spiele gab es schon im alten Griechenland.",
        "Did you know? The Olympic Games already existed in ancient Greece.",
    ),
    (
        "Wusstest du? Das Rad ist mehr als 5000 Jahre alt.",
        "Did you know? The wheel is more than 5,000 years old.",
    ),
    (
        "Wusstest du? Die alten Römer bauten Straßen, die zum Teil noch heute zu sehen sind.",
        "Did you know? The ancient Romans built roads, some of which can still be seen today.",
    ),
    (
        "Wusstest du? Regenwürmer lockern den Boden und helfen Pflanzen beim Wachsen.",
        "Did you know? Earthworms loosen the soil and help plants grow.",
    ),
    (
        "Wusstest du? Die Ägypter schrieben mit Hieroglyphen, kleinen Bildzeichen.",
        "Did you know? The ancient Egyptians wrote in hieroglyphs, little picture symbols.",
    ),
    (
        "Wusstest du? Die Wikinger fuhren auf schnellen Langschiffen über das Meer.",
        "Did you know? The Vikings sailed the seas in fast longships.",
    ),
    (
        "Wusstest du? Mammuts lebten noch, als in Ägypten schon Pyramiden standen.",
        "Did you know? Mammoths were still around when pyramids already stood in Egypt.",
    ),
    (
        "Wusstest du? Auf Burgen lebten Ritter. Dicke Mauern und Türme boten Schutz.",
        "Did you know? Knights lived in castles. Thick walls and towers gave protection.",
    ),
    # Technik
    (
        "Wusstest du? Computer rechnen nur mit Nullen und Einsen.",
        "Did you know? Computers only calculate with zeros and ones.",
    ),
    ("Wusstest du? Ein Byte besteht aus acht Bit.", "Did you know? One byte is eight bits."),
    (
        "Wusstest du? Flugzeuge fliegen, weil ihre Tragflächen Auftrieb erzeugen.",
        "Did you know? Planes fly because their wings create lift.",
    ),
    (
        "Wusstest du? Die Brüder Wright flogen 1903 das erste Motorflugzeug.",
        "Did you know? The Wright brothers flew the first powered aeroplane in 1903.",
    ),
    (
        "Wusstest du? Glasfaserkabel schicken Daten als Lichtblitze.",
        "Did you know? Fibre-optic cables send data as flashes of light.",
    ),
    (
        "Wusstest du? Solarzellen machen aus Sonnenlicht Strom.",
        "Did you know? Solar cells turn sunlight into electricity.",
    ),
    (
        "Wusstest du? Das Wort Roboter kommt aus dem Tschechischen und bedeutet schwere Arbeit.",
        "Did you know? The word robot comes from Czech and means hard work.",
    ),
    (
        "Wusstest du? Eine Kompassnadel zeigt dank des Erdmagnetfelds nach Norden.",
        "Did you know? A compass needle points north thanks to Earth's magnetic field.",
    ),
    (
        "Wusstest du? 3D-Drucker bauen Dinge Schicht für Schicht auf.",
        "Did you know? 3D printers build things layer by layer.",
    ),
    (
        "Wusstest du? Schall ist unter Wasser schneller als in der Luft.",
        "Did you know? Sound travels faster in water than in air.",
    ),
    (
        "Wusstest du? GPS-Satelliten im All helfen, deinen Standort zu finden.",
        "Did you know? GPS satellites in space help find where you are.",
    ),
    (
        "Wusstest du? Windräder wandeln Wind in Strom um.",
        "Did you know? Wind turbines turn wind into electricity.",
    ),
]

# --- Tageszeit-Grüße ------------------------------

_GRUESSE = [
    ("Guten Morgen!", "Good morning!", {"t": "morgen"}),
    ("Guten Morgen, Sonnenschein!", "Good morning, sunshine!", {"t": "morgen"}),
    ("Hallo, du Frühaufsteher!", "Hello, early bird!", {"t": "morgen"}),
    ("Moin, moin!", "Rise and shine!", {"t": "morgen"}),
    ("Schön, dass ihr da seid!", "So good to see you all!", {"t": "morgen"}),
    ("Mahlzeit!", "Lunchtime!", {"t": "mittag"}),
    ("Guten Appetit zusammen!", "Enjoy your meal, everyone!", {"t": "mittag"}),
    ("Hallo, Mittagsbande!", "Hello, lunch crew!", {"t": "mittag"}),
    ("Guten Tag!", "Good afternoon!", {"t": "nachmittag"}),
    ("Schönen Nachmittag!", "Have a lovely afternoon!", {"t": "nachmittag"}),
    ("Hallo, ihr Lieben!", "Hello, lovely people!", {"t": "nachmittag"}),
    ("Willkommen zurück!", "Welcome back!", {"t": "nachmittag"}),
    ("Guten Abend!", "Good evening!", {"t": "abend"}),
    ("Schönen Abend!", "Have a lovely evening!", {"t": "abend"}),
    ("Hallo, Abendstern!", "Hello, evening star!", {"t": "abend"}),
    ("Feierabend-Gruß an alle!", "Evening greetings to everyone!", {"t": "abend"}),
    ("Gute Nacht!", "Good night!", {"t": "nacht"}),
    ("Schlaf gut und träum was Schönes!", "Sleep well and dream something nice!", {"t": "nacht"}),
    ("Pssst, die Nacht ist da.", "Shh, it's night time.", {"t": "nacht"}),
    ("Hallo, Nachteule!", "Hello, night owl!", {"t": "nacht"}),
    ("Schön, dass du da bist!", "Great to have you here!"),
    ("Hallo, Familie!", "Hello, family!"),
]

EINTRAEGE = (
    _bauen("spruch", _SPRUECHE)
    + _bauen("weisheit", _WEISHEITEN)
    + _bauen("fakt", _FAKTEN)
    + _bauen("gruss", _GRUESSE)
)


def tageszeit(stunde):
    """Tageszeit-Schlüssel zur Stunde (0-23)."""
    if 5 <= stunde < 11:
        return "morgen"
    if 11 <= stunde < 14:
        return "mittag"
    if 14 <= stunde < 18:
        return "nachmittag"
    if 18 <= stunde < 22:
        return "abend"
    return "nacht"


def jahreszeit(monat):
    """Jahreszeit-Schlüssel zum Monat (1-12), meteorologisch."""
    if monat in (3, 4, 5):
        return "fruehling"
    if monat in (6, 7, 8):
        return "sommer"
    if monat in (9, 10, 11):
        return "herbst"
    return "winter"


def passend(eintrag, *, tageszeit_, wochentag, jahreszeit_):
    """Gilt der Eintrag zu dieser Tageszeit, diesem Wochentag (0 = Montag) und dieser Jahreszeit?"""
    if eintrag["tageszeit"] not in ("egal", tageszeit_):
        return False
    if eintrag["wochentage"] is not None and wochentag not in eintrag["wochentage"]:
        return False
    return eintrag["jahreszeit"] in ("egal", jahreszeit_)
