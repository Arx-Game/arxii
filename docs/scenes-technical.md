# Scenes Technical Implementation

This document outlines the technical implementation of the scenes system in Arx II, focusing on the database design and message attribution through the guise system.

## Problem Statement

In Arx I, scenes (called RPEvents) used raw text log files to store roleplay content. This approach had significant limitations:

- **Poor metadata support**: Raw text couldn't properly attribute messages to their sources
- **No scope visibility**: Couldn't represent different levels of who could see what content
- **No rich media**: Couldn't attach images or other media to messages
- **Limited presentation**: No visual enhancements for improved reading experience

## Database-Driven Approach

Arx II moves all scene data into the database, enabling rich metadata, proper attribution, and enhanced presentation features.

### Core Tables

#### Scenes
- Scene metadata (title, description, date, participants)
- Associated Story connections
- GM permissions and trust levels
- Scene state (active, completed, archived)

#### Messages
- Individual messages within scenes
- Timestamp and ordering
- Content (text, potentially rich formatting)
- Associated guise for display
- Scope/visibility settings

#### Guises
The key innovation for message attribution and presentation.

## Guise System

### Purpose
Guises solve the attribution problem by providing a flexible system for how messages appear while maintaining staff visibility into who actually sent them.

### Guise Table Structure
- **ID**: Primary key
- **Character**: Foreign key to the owning character
- **Name**: Display name for this guise
- **Description**: Physical description text
- **Thumbnail**: Image reference for visual presentation
- **Created**: Timestamp
- **Is_Default**: Boolean flag for character's standard guise

### Use Cases

#### Standard Roleplay
- Characters have a default guise representing their normal appearance
- Messages display with character's name, description, and portrait

#### Disguises and Masks
- Players create additional guises when wearing disguises
- Messages show the disguised identity instead of true character
- Staff can always see the real sender for moderation

#### Transformation Magic
- Magical shape-changing creates temporary guises
- Players can switch between forms within scenes
- Visual representation changes with magical state

#### GM Messages
- GMs can send messages as NPCs or environmental narration
- Each NPC can have their own guise with appropriate imagery
- Maintains immersion while allowing staff oversight

### Message Attribution Flow

1. **Player sends message**: Associates with selected guise
2. **Display to players**: Shows guise name, description, thumbnail
3. **Staff visibility**: Always shows real character behind guise
4. **Logging**: Preserves both guise display and true attribution

## Frontend Integration

### Visual Novel Presentation
- Thumbnail images appear next to messages
- Different guises show different portraits
- Creates visual variety and character recognition
- Enhances scene readability and engagement

### Guise Selection
- Players can switch active guises during scenes
- UI shows available guises for character
- Preview of how messages will appear
- Quick selection for common disguises/forms

### Rich Scene Display
- Messages grouped by speaker/guise
- Thumbnail galleries for scene participants
- Timestamp and scope indicators
- Enhanced formatting for different message types

## Technical Benefits

### Data Integrity
- Foreign key relationships ensure data consistency
- Proper indexing for efficient queries
- Structured data enables advanced features

### Query Capabilities
- Find all messages by a specific character across scenes
- Filter by guise to track disguised activities
- Scope-based visibility for different user types
- Rich search and filtering options

### Extensibility
- Easy to add new message types
- Guise system supports future features (voice clips, animations)
- Database structure supports complex scene mechanics
- Migration path from text logs to structured data

## Implementation Considerations

### Performance
- Proper indexing on frequently queried fields
- Efficient loading of scene messages with guises
- Caching strategies for active scenes
- Pagination for large scene logs

### Privacy and Moderation
- Staff always see real character attribution
- Player privacy settings for guise visibility
- Moderation tools work with true identities
- Audit trails for accountability

### Migration Strategy
- New scenes use database system from launch
- Legacy text logs can be preserved separately
- No need to import old scene data
- Focus on matching player functionality expectations
