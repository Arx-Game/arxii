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
