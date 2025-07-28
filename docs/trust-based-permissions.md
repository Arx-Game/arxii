# Trust-Based Permission System Design

**Status**: Design Document - Implementation TBD

## Overview

Arx II implements a granular trust-based permission system that differs significantly from Evennia's standard role-based hierarchy. This system empowers trusted players to act as GMs with specific, bounded permissions based on demonstrated trustworthiness.

## Core Principles

### Trust Over Roles
- **Earned Trust**: Permissions granted based on demonstrated trustworthiness over time
- **Granular Scope**: Specific permissions for specific tasks, not broad administrative access
- **Revocable**: Trust can be revoked if abused or circumstances change
- **Transparent**: Players understand what permissions they have and why

### Player GM Empowerment
- **Story Responsibility**: Player GMs responsible for specific stories, domains, or character types
- **Limited Django Access**: Player GMs typically don't get Django admin site access
- **Bounded Authority**: Powers are scoped to specific areas of responsibility
- **Audit Trail**: All GM actions logged for review and accountability

## Permission Categories

### Roster Management
- **Character Approval**: Approve applications for specific character types or houses
- **Roster Movement**: Move characters between rosters (Active ↔ Inactive)
- **Application Review**: Review and provide feedback on character applications

### Story Management
- **Plot Authority**: Run stories within specific domains or themes
- **NPC Control**: Control NPCs relevant to their stories
- **Event Coordination**: Organize and run community events
- **Resource Allocation**: Distribute story-specific resources or rewards

### Administrative Support
- **Conflict Resolution**: Mediate player disputes in specific contexts
- **New Player Guidance**: Mentor new players and help with onboarding
- **Community Moderation**: Handle minor rule violations or social issues

## Implementation Strategy

### Trust Scoring System (Future)
```python
# Example trust model (not yet implemented)
class PlayerTrust(models.Model):
    player_data = models.OneToOneField(PlayerData, on_delete=models.CASCADE)
    overall_trust_score = models.IntegerField(default=0)
    roster_trust = models.IntegerField(default=0)
    story_trust = models.IntegerField(default=0)
    admin_trust = models.IntegerField(default=0)
    # Trust built through consistent, positive actions over time
```

### Permission Scoping
```python
# Example permission model (not yet implemented)
class TrustPermission(models.Model):
    player_data = models.ForeignKey(PlayerData, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=50)  # 'roster_approve', 'story_gm', etc.
    scope = models.CharField(max_length=100)  # 'house_grayson', 'crownlands_politics', etc.
    granted_by = models.ForeignKey(PlayerData, on_delete=models.SET_NULL, null=True)
    granted_date = models.DateTimeField(auto_now_add=True)
    expires_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
```

## Integration with Roster System

### Character Application Approval
- Trusted players can approve applications for characters within their scope
- Example: House Grayson's trusted player GM can approve applications for Grayson family members
- Approval creates proper RosterTenure with audit trail

### Story-Driven Character Management
- Player GMs can temporarily move characters between rosters for story purposes
- Example: Moving a character to "Inactive" during a story absence, then back to "Active"
- All movements logged with justification and reviewer information

## Security Considerations

### Preventing Abuse
- **Audit Logging**: All trust-based actions logged with full context
- **Peer Review**: Important decisions can require multiple trusted players to agree
- **Staff Oversight**: Staff can review and revoke trust permissions at any time
- **Limited Scope**: Permissions never grant broad system access

### Gradual Trust Building
- **Start Small**: New trusted players start with very limited permissions
- **Prove Reliability**: Expand permissions based on consistent good judgment
- **Community Input**: Other players can provide feedback on trusted player performance

## Command Integration

When implementing roster commands, consider trust-based permissions:

```python
# Example command permission check (pseudocode)
def can_approve_application(player_data, application):
    # Check if player has roster approval trust for this character type
    character_house = application.character.house
    return player_data.has_trust_permission('roster_approve', f'house_{character_house.name.lower()}')
```

## Future Considerations

### Automation Integration
- **Trust Score Automation**: Some permissions granted automatically based on trust metrics
- **Community Voting**: Players can vote to grant or revoke trust in specific areas
- **Performance Metrics**: Track success/failure rates of trust-based decisions

### Scaling Challenges
- **Trust Inflation**: Prevent everyone from eventually getting all permissions
- **Quality Control**: Maintain standards as more players gain trust
- **Conflict Resolution**: Handle disputes between trusted players

## Related Systems

This trust-based permission system will integrate with:
- **Roster Management**: Character application approval and roster movement
- **Story System**: Plot authority and NPC control
- **Communication**: Mail approval, channel moderation
- **Economy**: Resource allocation and transaction approval

---

**Note**: This is a design document. Implementation details will be refined as we build the system incrementally.
