# Homepage Plan

The homepage introduces players to the world of **Arx II** and points them toward current activity. It highlights scenes and stories players can join while giving newcomers quick orientation.

## Scenes and Stories

Scenes and stories are the heart of Arx II and outrank news and community content in prominence. Both the navigation bar and homepage quick actions should list **Scenes** before **News** and **Community** so players are immediately drawn toward active narrative play.

### ScenesSpotlight

The `ScenesSpotlight` component surfaces in-progress and recently concluded scenes, reinforcing the game's storytelling focus. It fetches data from `/api/scenes/spotlight/` and expects two arrays:

- `in_progress` – scene objects with `id`, `title`, and participant info for currently running stories.
- `recent` – recently finished scenes with the same structure.

By highlighting these scenes, the spotlight invites players to jump into ongoing narratives or follow up on recent events.

## Layout Summary

- **Navigation** – Global menu lists **Scenes**, **News**, and **Community** in that order to emphasize storytelling.
- **Hero** – Tagline and call to action alongside a striking background. Optionally include a brief teaser of active stories.
- **Quick Actions** – Buttons list a featured scene first, followed by links to News and Community, alongside login, account creation, and resume options.
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
  - Featured scene ID followed by links to News and Community.
- **ScenesSpotlight**
  - Endpoint `/api/scenes/spotlight/` returning `in_progress` and `recent` scenes.
  - Each scene includes `id`, `title`, and participant list with avatar URLs.
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
