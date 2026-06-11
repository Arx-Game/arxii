# Evennia Quirks

Evennia-specific quirks and integration patterns. Consult when touching migrations, makemigrations, or evennia_extensions.

### Evennia makemigrations Solution
**FIXED: Custom makemigrations command prevents phantom Evennia library migrations**

We have a custom `makemigrations` command that prevents Django from creating problematic migrations in Evennia's library when our models have ForeignKeys to Evennia models.

```bash
# SAFE - our custom command prevents phantom Evennia migrations
arx manage makemigrations

# Still works - specify specific apps when needed  
arx manage makemigrations traits
```

**Details**: See `core_management/CLAUDE.md` for full technical documentation of the solution.

### Evennia Integration Strategy
- **Use Evennia Models**: Keep using Evennia's Account, ObjectDB, etc. - don't reinvent the wheel
- **Extend via evennia_extensions**: Use the evennia_extensions app pattern for data storage that extends Evennia models
- **No Attributes**: Replace all Evennia attribute usage with proper Django models through evennia_extensions
- **Item Data System**: Consider reusing ArxI's item_data descriptor system for routing data to different storage models

### Migration Management for New Apps
**IMPORTANT: When working on a new app, avoid multiple migrations during development**
django_notes.md gives a more in-depth explanation of this strategy.

### loaddata Cannot UPDATE SharedMemoryModel Rows (#946)

**Natural-key `loaddata` INSERTS fine but silently no-ops UPDATES on every
SharedMemoryModel** (= every concrete model in this repo). Django's
deserializer resolves the existing pk via `get_by_natural_key` — which loads
the row into the idmapper identity map — then constructs `Model(**data)` with
that pk, and the identity map intercepts construction-by-pk and returns the
**cached old instance**, discarding the fixture's new field values. No error
is raised. Verified cross-process during #944; flushing the cache around
`loaddata` doesn't help because `get_by_natural_key` itself re-primes the
cache mid-deserialization.

**Rules:**

- Fixture JSON is valid for **fresh-database seeding only** (pure inserts).
- Never rely on re-loading an edited fixture to update existing rows — use an
  explicit upsert: `core_management.content_fixtures.load_entries` (the #944
  content pipeline, `just load-content`) or `update_or_create` keyed on the
  natural fields.
- Don't build cache-flush workarounds; upsert is the standing answer (the
  identity map is load-bearing — see the `sharedmemory-model` skill).
