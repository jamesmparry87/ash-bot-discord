# !testreminder Command Usage Guide

## Overview
The `!testreminder` command tests the scheduled message delivery system by creating a temporary scheduled message that will be sent to the Newt Mods channel after a specified delay.

## Purpose
- Test that the scheduled messaging infrastructure is working correctly
- Validate that Monday morning messages, Friday messages, and other automated protocols will function as expected
- Provide immediate feedback on system reliability

## Usage

### Basic Usage
```
!testreminder [delay]
```

### Examples
```
!testreminder           # Default 2 minute test
!testreminder 30s       # Test in 30 seconds
!testreminder 5m        # Test in 5 minutes  
!testreminder 1h        # Test in 1 hour
```

### Supported Time Formats
- `s` - seconds (minimum: 10 seconds)
- `m` - minutes  
- `h` - hours
- `d` - days (maximum: 1 hour for testing)

## Permissions
- **Moderators only** - Requires `manage_messages` permission
- Command can be used in any channel, but test message always goes to **Newt Mods**

## Process Flow

1. **Command Execution**: Moderator runs `!testreminder [delay]`
2. **Validation**: System validates time format and permissions
3. **Immediate Confirmation**: Bot sends confirmation message with test parameters
4. **Scheduled Delivery**: After the specified delay, test message appears in Newt Mods channel

## Test Message Format

The test message delivered to Newt Mods includes:
- Test completion confirmation
- Timing details (initiated, scheduled, actual delivery times)  
- System status validation
- Confirmation that other scheduled messages should work correctly

## Error Handling

- **Invalid time format**: Clear error message with examples
- **Too short delay**: Minimum 10 seconds required for system reliability
- **Too long delay**: Maximum 1 hour for testing purposes
- **Permission errors**: Clear feedback if bot can't access target channel
- **Delivery failures**: Error messages sent to target channel when possible

## Integration

This command uses the same scheduling mechanism as:
- Monday morning greetings (9 AM UK time)
- Friday morning messages (9 AM UK time)  
- Trivia Tuesday automation
- Other automated Discord messages

If `!testreminder` works correctly, these other scheduled functions should also work properly.

## Technical Details

- **Target Channel**: Always sends to Newt Mods (ID: 1213488470798893107)
- **Timezone**: Uses UK time (Europe/London timezone)
- **Scheduling**: Uses `asyncio.create_task()` for non-blocking delays
- **Accuracy**: Typically accurate to within 1 second
