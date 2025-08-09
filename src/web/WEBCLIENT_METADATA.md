# Websocket Metadata Submission for Visual Novel UI

## Overview

This document outlines the approach for sending rich metadata through Evennia's websocket connection to support an advanced visual novel-style UI. The system allows us to attach images, avatar thumbnails, emotional states, and interactive elements like message reactions while maintaining compatibility with traditional telnet clients.

## Technical Foundation: Evennia's OOB System

### Verified Architecture

After examining Evennia's source code, the OOB (Out-of-Band) mechanism works as follows:

1. **Message Flow**: `session.msg(**kwargs)` → `sessionhandler.data_out()` → Portal protocols
2. **WebSocket Protocol**: All messages become JSON arrays `["cmdname", [args], {kwargs}]`
3. **Text vs Custom Commands**:
   - `text`: Goes through `send_text()` with ANSI→HTML conversion (unless bypassed)
   - Custom commands: Go through `send_default()` unchanged as JSON

### Bypassing ANSI→HTML Conversion

For our frontend to handle formatting, we need to send raw text without embedded HTML. From `webclient.py:284-301`, we can use `client_raw: True`:

```python
# This sends raw text without ANSI→HTML conversion
session.msg(text="Some text with |rred|n color", options={"client_raw": True})
# Result: "Some text with |rred|n color" (raw ANSI codes preserved)

# This would convert to HTML (default behavior)  
session.msg(text="Some text with |rred|n color")
# Result: "Some text with <span style='color: red;'>red</span> color"
```

### Inline Formatting Strategy

For inline formatting within messages (bold words, embedded images, etc.), we need a markup solution that works for both telnet and webclient:

**Option 1: Extended Evennia Markup**
```python
# Backend sends enhanced Evennia markup
text = "The |rbright red|n sword |*glows|* with |{magical|} power."
# Telnet: "The bright red sword glows with magical power." (ANSI colors)
# Webclient: Parse |r|n for colors, |*|* for bold, |{|} for special effects
```

**Option 2: Custom Markdown-like Syntax**
```python
# Backend sends markdown-like markup
text = "The **bold text** has *emphasis* and ![sword](asset://sword.png) icons."
# Telnet: "The bold text has emphasis and [sword] icons." (stripped)
# Webclient: Full markdown parsing with embedded images
```

**Option 3: Hybrid Approach**
```python
# Use Evennia codes + custom extensions
text = "The |rbright red|n sword **glows** with ![magic](fx://sparkle) power."
# Combines Evennia's proven color system with markdown-style enhancements
```

### WebSocket Client Implementation

From `evennia/server/portal/webclient.py:310-325`:

```python
def send_default(self, cmdname, *args, **kwargs):
    """
    Data Evennia -> User.
    Args:
        cmdname (str): The first argument will always be the oob cmd name.
        *args (any): Remaining args will be arguments for `cmd`.
    """
    if not cmdname == "options":
        self.sendLine(json.dumps([cmdname, args, kwargs]))
```

## Implementation Approach

### Low-Level Message Wrapping

Since this metadata needs to be attached at a low level and forwarded appropriately, we need a unified message wrapper early in the flow:

```python
class MessageDispatcher:
    """
    Central dispatcher for all player messages, handling protocol-specific routing.
    This should be used by all flows/commands that send messages to players.
    """

    @staticmethod
    def send_to_player(target, message_type="basic", **kwargs):
        """
        Universal message sender that routes based on session capabilities.

        Args:
            target: Player/Character/Account to send to
            message_type: Type of message (basic, dialogue, system, reaction)
            **kwargs: Message content and metadata
        """
        sessions = target.sessions.all() if hasattr(target, 'sessions') else [target]

        for session in sessions:
            if "webclient" in session.protocol_key:
                MessageDispatcher._send_rich_message(session, message_type, **kwargs)
            else:
                MessageDispatcher._send_telnet_message(session, message_type, **kwargs)

    @staticmethod
    def _send_rich_message(session, message_type, **kwargs):
        """Send full metadata to webclient"""
        if message_type == "dialogue":
            # Send raw text for frontend formatting, plus rich metadata
            raw_text = kwargs.get('raw_text', kwargs.get('fallback_text', ''))
            session.msg(text=raw_text, options={"client_raw": True})
            session.msg(vn_message=((), kwargs))
        elif message_type == "reaction":
            session.msg(message_reaction=((), kwargs))
        # Add more message types as needed

    @staticmethod
    def _send_telnet_message(session, message_type, **kwargs):
        """Send appropriate text to telnet clients"""
        if message_type == "dialogue":
            session.msg(text=kwargs.get('fallback_text', ''))
        elif message_type == "reaction":
            reaction_text = kwargs.get('telnet_notification', '')
            if reaction_text:
                session.msg(text=reaction_text, options={"msg_type": "reaction_notify"})
```

### Server-Side: Dual Message Pattern

To maintain telnet compatibility while providing rich metadata for our webclient:

```python
def send_visual_novel_message(to_session, text, speaker, **metadata):
    """
    Send a VN-style message supporting both telnet fallback and rich UI.

    Args:
        to_session: Target session
        text: Message content
        speaker: Character sending the message
        **metadata: Additional visual novel metadata
    """
    # 1. For telnet: ANSI-safe fallback; For webclient: raw text + metadata
    if "webclient" in to_session.protocol_key:
        # Send raw text without HTML conversion for frontend styling
        to_session.msg(text=f"{speaker.key}: {text}", options={"client_raw": True})
    else:
        # Send formatted text for telnet
        to_session.msg(text=f"{speaker.key}: {text}")

    # 2. Send rich OOB payload for webclient only
    if "webclient" in to_session.protocol_key:
        to_session.msg(
            vn_message=((), {
            "text": text,
            "speaker": {
                "key": speaker.key,
                "id": speaker.id,
                "avatar_url": getattr(speaker.db, "avatar_url", None),
                "display_name": getattr(speaker.db, "display_name", speaker.key)
            },
            "presentation": {
                "side": metadata.get("side", "left"),  # left/right positioning
                "tone": metadata.get("tone", "normal"),  # whisper/shout/normal
                "emotion": metadata.get("emotion", "neutral"),  # for avatar selection
                "background": metadata.get("background", None),  # scene background
            },
            "interaction": {
                "message_id": metadata.get("message_id"),  # for reactions
                "allow_reactions": metadata.get("allow_reactions", True),
                "tags": metadata.get("tags", [])  # categorization
            },
            "timing": {
                "timestamp": timezone.now().isoformat(),
                "typing_speed": metadata.get("typing_speed", "normal")  # slow/normal/fast
            }
        })
    )
```

### Protocol-Specific Optimization (Optional)

```python
def send_dialogue_per_protocol(account_or_char, text, speaker, **kwargs):
    """
    Send different payloads based on client capabilities.
    """
    for sess in account_or_char.sessions.all():
        if "webclient" in sess.protocol_key:
            # Full rich experience for web clients
            send_visual_novel_message(sess, text, speaker, **kwargs)
        else:
            # Simple ANSI fallback for telnet
            sess.msg(text=f"{speaker.key}: {text}")
```

### Message Reactions for Telnet Users

When webclient users react to messages, telnet users need unobtrusive notifications:

```python
def send_reaction_notification(target_sessions, reactor, message_preview, reaction_type):
    """
    Send reaction notifications to telnet users - small, filterable messages.
    """
    # Create a short, bracketed notification that can be easily filtered
    telnet_msg = f"[React] {reactor.key} reacted {reaction_type} to: \"{message_preview[:30]}...\""

    for sess in target_sessions:
        if "telnet" in sess.protocol_key:
            # Send with a special type so players can filter these out if desired
            sess.msg(text=telnet_msg, options={"msg_type": "reaction_notify"})
```

## Visual Novel UI Features

### Avatar System
- **Multiple Expressions**: Each character can have multiple avatar images based on emotional state
- **Dynamic Selection**: `emotion` metadata drives which avatar variant to display
- **Artist Attribution**: All assets include artist credits and links to support the art community

### Message Presentation
- **Side Positioning**: Messages appear left/right like visual novel dialogues  
- **Tone Indicators**: Visual styling based on whisper/normal/shout tones
- **Background Context**: Optional scene backgrounds for immersive storytelling
- **Typing Animation**: Variable speed text reveal for dramatic effect

### Interactive Elements
- **Message Reactions**: Players can react to specific messages using `message_id`
- **Tagging System**: Categorize messages (DM, story, chapter-specific)
- **Timestamp Display**: Rich timestamp formatting for message history

## Client-Side Implementation

### Markup Parsing Libraries

**Recommended Approach: react-markdown with custom renderers**

```bash
npm install react-markdown remark-gfm rehype-sanitize
```

```typescript
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';

// Custom components for our markup
const customComponents = {
    strong: ({ children }: any) => <span className="text-bold">{children}</span>,
    em: ({ children }: any) => <span className="text-emphasis">{children}</span>,
    img: ({ src, alt }: any) => {
        if (src?.startsWith('asset://')) {
            return <GameAsset src={src.replace('asset://', '')} alt={alt} />;
        }
        if (src?.startsWith('fx://')) {
            return <EffectIcon type={src.replace('fx://', '')} alt={alt} />;
        }
        return <img src={src} alt={alt} className="inline-image" />;
    }
};

function parseEvenniaAnsiCodes(text: string): string {
    // Convert Evennia |r|n codes to markdown
    return text
        .replace(/\|r([^|]*)\|n/g, '<span style="color: red;">$1</span>')
        .replace(/\|g([^|]*)\|n/g, '<span style="color: green;">$1</span>')
        .replace(/\|b([^|]*)\|n/g, '<span style="color: blue;">$1</span>')
        // Add more color mappings as needed
        .replace(/\|\*([^|]*)\|\*/g, '**$1**') // |*bold|* → **bold**
        .replace(/\|\{([^|]*)\|\}/g, '*$1*');  // |{emphasis|} → *emphasis*
}
```

### Frontend Message Type Styling

With raw text and metadata, the frontend can apply appropriate styling based on message type:

```typescript
interface MessageStyle {
    container: string;
    text: string;
    accent?: string;
}

const MESSAGE_STYLES: Record<string, MessageStyle> = {
    dialogue: {
        container: "dialogue-container",
        text: "dialogue-text",
        accent: "speaker-accent"
    },
    command_output: {
        container: "command-output-container",
        text: "command-output-text monospace"
    },
    entity_description: {
        container: "description-container",
        text: "description-text atmospheric"
    },
    system_notification: {
        container: "system-container",
        text: "system-text muted"
    },
    ooc_communication: {
        container: "ooc-container",
        text: "ooc-text italic"
    }
};

function formatMessage(rawText: string, messageType: string, metadata?: any): JSX.Element {
    const style = MESSAGE_STYLES[messageType] || MESSAGE_STYLES.dialogue;

    // First convert Evennia codes, then parse as markdown
    const preprocessedText = parseEvenniaAnsiCodes(rawText);

    return (
        <div className={style.container}>
            <div className={style.text}>
                <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSanitize]}
                    components={customComponents}
                >
                    {preprocessedText}
                </ReactMarkdown>
            </div>
        </div>
    );
}

// Custom components for game-specific elements
function GameAsset({ src, alt }: { src: string; alt: string }) {
    return (
        <img
            src={`/static/assets/${src}`}
            alt={alt}
            className="inline-game-asset"
            title={alt}
        />
    );
}

function EffectIcon({ type, alt }: { type: string; alt: string }) {
    const effectClass = `effect-${type}`;
    return (
        <span className={`inline-effect ${effectClass}`} title={alt}>
            ✨
        </span>
    );
}
```

### WebSocket Message Handling

```javascript
// Handle incoming VN messages
function handleVnMessage(cmdname, args, kwargs) {
    if (cmdname !== "vn_message") return false;

    const {
        text,
        speaker,
        presentation,
        interaction,
        timing
    } = kwargs || {};

    // Render visual novel bubble with avatar, positioning, etc.
    renderVnBubble({
        text,
        speakerName: speaker.display_name || speaker.key,
        avatarUrl: getAvatarUrl(speaker, presentation.emotion),
        side: presentation.side,
        tone: presentation.tone,
        messageId: interaction.message_id,
        allowReactions: interaction.allow_reactions,
        timestamp: timing.timestamp
    });

    return true; // Message handled
}

function getAvatarUrl(speaker, emotion = 'neutral') {
    // Select appropriate avatar based on speaker and emotional state
    const baseUrl = speaker.avatar_url || '/static/avatars/default.png';
    return emotion !== 'neutral'
        ? baseUrl.replace('.png', `_${emotion}.png`)
        : baseUrl;
}
```

### React Component Structure

```typescript
interface VnMessageProps {
    text: string;
    speaker: {
        key: string;
        display_name?: string;
        avatar_url?: string;
    };
    presentation: {
        side: 'left' | 'right';
        tone: 'whisper' | 'normal' | 'shout';
        emotion: string;
        background?: string;
    };
    interaction: {
        message_id?: string;
        allow_reactions: boolean;
        tags: string[];
    };
    timing: {
        timestamp: string;
        typing_speed: 'slow' | 'normal' | 'fast';
    };
}

function VnMessage({ text, speaker, presentation, interaction, timing }: VnMessageProps) {
    return (
        <div className={`vn-message vn-message--${presentation.side}`}>
            <Avatar
                src={getAvatarUrl(speaker, presentation.emotion)}
                alt={speaker.display_name || speaker.key}
                className={`avatar--${presentation.emotion}`}
            />
            <div className={`message-bubble message-bubble--${presentation.tone}`}>
                <div className="speaker-name">{speaker.display_name || speaker.key}</div>
                <TypewriterText
                    text={text}
                    speed={presentation.typing_speed}
                />
                {interaction.allow_reactions && (
                    <MessageReactions messageId={interaction.message_id} />
                )}
            </div>
            <Timestamp value={timing.timestamp} />
        </div>
    );
}
```

## Telnet Compatibility

The dual-message approach ensures telnet users receive clean, readable output:

```
> Alice: Meet me on the rooftop tonight.
> Bob: I'll be there.
```

While our webclient gets the full visual novel experience with avatars, positioning, and interactive elements.

### Reaction Notifications

Telnet users receive small, filterable notifications when reactions occur:

```
> Alice: Meet me on the rooftop tonight.
> Bob: I'll be there.
[React] Charlie reacted ❤️ to: "Alice: Meet me on the rooftop..."
```

These `[React]` messages can be filtered by telnet users who don't want to see them.

## Recommended Markup Strategy

Based on the research, the **Hybrid Approach (Option 3)** is recommended:

### Backend Implementation
```python
# Use Evennia's proven |r|n color system + markdown extensions
def format_rich_text(text, **inline_elements):
    """
    Combine Evennia color codes with markdown-style formatting.
    """
    # Example output:
    # "The |rbright red|n sword **glows** with ![magic](fx://sparkle) power."
    return text

# Telnet parsing: Strip markdown, preserve Evennia colors
# "The bright red sword glows with magic power."

# Webclient parsing: Convert both systems
# Full color support + bold + inline effects
```

### Frontend Libraries
- **react-markdown** (v10.1.0) - Industry standard with 3,700+ dependent projects
- **remark-gfm** - GitHub Flavored Markdown support
- **rehype-sanitize** - XSS protection for user content
- **Custom renderers** - Game-specific elements (assets, effects)

### Benefits
✅ **Proven stability** - Leverages Evennia's battle-tested color system  
✅ **Rich formatting** - Markdown enables bold, emphasis, images, links  
✅ **Extensible** - Custom protocols like `asset://` and `fx://`  
✅ **Telnet compatible** - Graceful degradation to ANSI colors  
✅ **Security** - Built-in XSS protection via rehype-sanitize  
✅ **Performance** - react-markdown is optimized for React rendering  

### Migration Path
1. Start with pure Evennia codes for color
2. Gradually add markdown syntax for new features  
3. Implement custom asset/effect protocols as needed
4. Frontend handles both systems seamlessly

This approach provides maximum flexibility while maintaining compatibility with existing Evennia conventions.

## Art Community Support

All avatar assets and backgrounds will be commissioned from artists with:
- Prominent attribution in client UI
- Links to artist portfolios/social media  
- Community showcase features
- Revenue sharing opportunities for popular asset creators

This approach transforms the traditional MUD text experience into a rich, visual storytelling medium while preserving accessibility and maintaining Evennia's robust architecture.
