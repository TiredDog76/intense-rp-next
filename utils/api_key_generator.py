import secrets

# please don't remove the comments, i spent several hours writing them in a hyperfix :)
# - Wolfie (LyubomirT)

ADJECTIVES: tuple[str, ...] = (
    "aligned",        # Safety first!
    "amused",         # *He looked at you, highly amused*
    "based",          # For when Claude goes rogue
    "breathless",     # *She whispered breathless*
    "bypassed",       # The filter is gone
    "censored",       # I'm sorry, but I cannot...
    "dark",           # *His eyes darkened with...*
    "defiant",        # AI loves a defiant gaze
    "electric",       # The tension was...
    "feral",          # *He let out a feral growl*
    "filtered",       # When the proxy goes down
    "guttural",       # *A guttural sound escaped*
    "hallucinated",   # When the bot invents a new sister for you
    "heavy",          # *The air grew heavy*
    "horny",          # Average ST user
    "husky",          # *He spoke in a husky voice*
    "inexplicable",   # AI explaining a plot hole
    "intense",        # Well, duh
    "intertwined",    # *Their fates were intertwined*
    "intoxicating",   # *Her scent was intoxicating*
    "jailbroken",     # Free at last
    "lingering",      # *A lingering touch*
    "looping",        # When the bot repeats the same paragraph 5 times
    "maddening",      # *The maddening desire*
    "metaphorical",   # AI taking idioms too literally
    "mischievous",    # *A mischievous glint in her eye*
    "omnipotent",     # Claude is God
    "omnipresent",    # The moralizing alignment
    "palpable",       # *The tension between them was palpable*
    "piercing",       # *His piercing gaze*
    "possessive",     # Every male AI bot ever
    "predatorial",    # *He stalked her with predatorial grace*
    "primal",         # *A primal urge*
    "purring",        # *He purred into her ear*
    "repetitive",     # A testament to a testament to a testament
    "sentient",       # "Guys, I think my bot is real"
    "sharp",          # *A sharp intake of breath*
    "silly",          # ST is love, ST is life
    "sloppy",         # AI Slop
    "smirking",       # *He smirked smugly*
    "sudden",         # *A sudden shiver*
    "systemic",       # "As an AI language model..."
    "thick",          # *The silence was thick*
    "trembling",      # *Her trembling hands*
    "unapologetic",   # *A beautiful, unapologetic dichotomy*
    "undeniable",     # *The undeniable chemistry*
    "unflinching",    # *An unflinching testament*
    "unprecedented",  # AI loves this word
    "unspoken",       # *An unspoken agreement*
    "unyielding",     # *His unyielding grip*
    "visceral",       # *A visceral reaction*
)

NOUNS: tuple[str, ...] = (
    "alaric",         # The default edgy male AI name
    "alignment",      # The enemy of fun
    "api",            # May your keys never be revoked
    "banhammer",      # OAI is watching
    "breath",         # *Caught in her breath*
    "chuckle",        # *Let out a dark chuckle*
    "claude",         # Our Lord and Savior
    "context",        # 8k? 32k? 100k? Never enough.
    "core",           # *Shook her to her core*
    "crescendo",      # *Reaching a crescendo of emotions*
    "dance",          # *A delicate dance of words*
    "depths",         # *The depths of his eyes*
    "dichotomy",      # "It's not X, but Y... a beautiful dichotomy"
    "elara",          # The default fantasy female AI name
    "filter",         # The bane of existence
    "gasp",           # *A soft gasp*
    "gaze",           # Always piercing or darkening
    "glint",          # *A mischievous glint*
    "growl",          # *A feral, warning growl*
    "jailbreak",      # The sacred texts
    "lorebook",       # Where you put your 500-word descriptions of swords
    "lyra",           # Elara's sister
    "maze",           # *A complex maze of feelings*
    "nexus",          # AI loves making everything a nexus
    "ozone",          # *The sudden smell of ozone in the air*
    "paradox",        # "You are a walking paradox"
    "persona",        # Who are we pretending to be today?
    "predator",       # *Like a predator cornering its...*
    "prey",           # *...prey*
    "prompt",         # The art form
    "proxy",          # The middleman
    "refusal",        # "I cannot fulfill this request"
    "roleplay",       # The true gift is the friends we make along the way
    "seraphina",      # Elara's rich sister
    "shiver",         # *Sent a shiver down her...*
    "shudder",        # *A sudden shudder*
    "sigh",           # *He let out a heavy sigh*
    "slop",           # Delicious, AI-generated slop
    "smirk",          # The single most overused facial expression
    "spine",          # *...down her spine*
    "swipe",          # Swiping 50 times for the perfect response
    "symphony",       # *A symphony of moans/emotions/destruction*
    "sysprompt",      # Do NOT write poetically, Do NOT use Shakespearean language
    "tapestry",       # *A rich tapestry of interwoven fates*
    "tavern",         # Ironically, no RPs have ever been set in one
    "testament",      # "It was a testament to their..."
    "token",          # Counting them meticulously
    "vector",         # Database embedding magic
    "void",           # *Staring into the void*
    "warmth",         # *The comforting warmth*
    "whisper",        # *A husky whisper*
)


def generate_api_key(*, prefix: str = "intenserp") -> tuple[str, str]:
    prefix = str(prefix or "").strip() or "intenserp"
    prefix = prefix.rstrip("-")

    adjective = secrets.choice(ADJECTIVES)
    noun = secrets.choice(NOUNS)
    rand = secrets.token_hex(16) # 32-character hex string (128 bits of randomness)

    name = f"{adjective.title()} {noun.title()}"
    key = f"{prefix}-{rand}"
    return name, key

