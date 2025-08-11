# Homepage Plan

The homepage introduces players to the world of **Arx II** and points them toward current activity. It highlights scenes and stories players can join while giving newcomers quick orientation.

## Layout Summary

- **Hero** – Tagline and call to action alongside a striking background. Optionally include a brief teaser of active stories.
- **Quick Actions** – Buttons for logging in, creating an account, resuming the last character, or jumping into a featured scene.
- **Live Snapshot** – Dynamic list of currently running scenes and stories so players can immediately see where action is happening.
- **New-player Tabs** – Collapsible panels or tabs that explain basic mechanics and link to onboarding content.
- **Lore Tabs** – Curated lore topics or featured articles to help players explore the setting.
- **Footer** – Links to policies, socials, and project information.

## Data Requirements

- **Hero**
  - Tagline text and background image.
  - Optional featured scene or story ID.
- **Quick Actions**
  - Authentication state for displaying login or resume options.
  - Character list for logged-in users.
  - Linkable scene or story IDs for direct entry.
- **Live Snapshot**
  - Feed of active scenes with title, location, participants, and joinable flag.
  - List of ongoing stories with summary and entry points.
- **New-player Tabs**
  - Structured onboarding content stored in the CMS.
- **Lore Tabs**
  - Lore categories and article summaries from the lore API.
- **Footer**
  - Static site links and configuration for external URLs.

## Optional / Deferrable Features

- Site-wide search or a command palette for quick navigation.
- Personalization such as favorited scenes or recently viewed lore.
- Animated backgrounds or parallax scrolling.

## Styling Guidelines

- Use **shadcn/ui** components for accessible, themeable primitives.
- Tailwind CSS provides layout, spacing, and typography utilities.
- Keep the layout mobile-first and responsive.

## Scenes and Stories Emphasis

The homepage must surface active **scenes** and **stories**. These represent the core gameplay loop—players browse ongoing narratives, join scenes in progress, and engage with evolving plots. The Live Snapshot should prominently feature open scenes and story hooks to invite immediate participation.
