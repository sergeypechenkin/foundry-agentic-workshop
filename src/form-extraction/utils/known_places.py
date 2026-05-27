"""Known cities and countries for semantic validation of place fields."""

KNOWN_PLACES: set[str] = {
    # UK cities
    'london', 'manchester', 'birmingham', 'leeds', 'glasgow', 'liverpool',
    'edinburgh', 'bristol', 'cardiff', 'belfast', 'dublin', 'oxford',
    'cambridge', 'york', 'bath', 'nottingham', 'sheffield', 'newcastle',
    'brighton', 'leicester', 'coventry', 'aberdeen', 'swansea', 'exeter',
    'plymouth', 'southampton', 'portsmouth', 'reading', 'derby', 'dundee',
    'wolverhampton', 'norwich', 'sunderland', 'stoke-on-trent', 'kingston',
    'croydon', 'luton', 'bolton', 'wigan', 'stockport', 'warrington',
    'slough', 'watford', 'guildford', 'chelmsford', 'maidstone', 'chester',
    'worcester', 'lincoln', 'carlisle', 'durham', 'winchester', 'canterbury',
    'stirling', 'inverness', 'perth', 'bangor', 'newport', 'st albans',
    # Countries
    'uk', 'united kingdom', 'gb', 'great britain', 'ireland', 'england',
    'scotland', 'wales', 'northern ireland',
    'usa', 'us', 'united states', 'united states of america',
    'france', 'germany', 'spain', 'italy', 'canada', 'australia',
    'netherlands', 'belgium', 'switzerland', 'austria', 'sweden', 'norway',
    'denmark', 'finland', 'portugal', 'greece', 'poland', 'czech republic',
    'hungary', 'romania', 'bulgaria', 'croatia', 'slovakia', 'slovenia',
    'new zealand', 'south africa', 'india', 'china', 'japan', 'brazil',
    'mexico', 'argentina', 'chile', 'colombia', 'nigeria', 'kenya', 'egypt',
    'turkey', 'russia', 'ukraine', 'israel', 'saudi arabia', 'uae',
    'singapore', 'hong kong', 'malaysia', 'thailand', 'indonesia',
    'philippines', 'vietnam', 'south korea', 'taiwan', 'pakistan',
    'bangladesh', 'sri lanka', 'nepal',
}
