import re
from typing import Dict, Optional

import discord


class EmbedCriteria:
    """Define criteria for embed monitoring"""

    def __init__(self, config: Dict):
        self.name = config.get("name", "Unknown Rule")
        self.bot_ids = config.get("bot_ids", [])
        self.trigger = config.get("trigger", {})
        self.action = config.get("action", {})

    def matches(self, message: discord.Message) -> bool:
        """Check if message matches criteria"""
        # Check if message is from monitored bot
        if self.bot_ids and message.author.id not in self.bot_ids:
            return False

        # Check if message has embeds
        if not message.embeds:
            return False

        embed = message.embeds[0]

        # Check title
        if "embed_title_contains" in self.trigger:
            if (
                not embed.title
                or self.trigger["embed_title_contains"].lower()
                not in embed.title.lower()
            ):
                return False

        if "embed_title_regex" in self.trigger:
            if not embed.title or not re.search(
                self.trigger["embed_title_regex"], embed.title
            ):
                return False

        # Check description
        if "embed_description_contains" in self.trigger:
            if (
                not embed.description
                or self.trigger["embed_description_contains"].lower()
                not in embed.description.lower()
            ):
                return False

        # Check field values
        if "field_value_greater_than" in self.trigger:
            field_check = self.trigger["field_value_greater_than"]
            field_name = field_check["field"]
            threshold = field_check["value"]

            for field in embed.fields:
                if field_name.lower() in field.name.lower():
                    try:
                        # Extract number from field value
                        numbers = re.findall(r"\d+", field.value)
                        if numbers and int(numbers[0]) > threshold:
                            return True
                    except:
                        pass
            return False

        # Check field existence
        if "has_field" in self.trigger:
            field_name = self.trigger["has_field"]
            if not any(
                field_name.lower() in field.name.lower() for field in embed.fields
            ):
                return False

        return True


def extract_user_from_embed(
    embed: discord.Embed, guild: discord.Guild
) -> Optional[discord.Member]:
    """Try to extract mentioned user from embed"""
    # Check description
    if embed.description:
        # Look for mention pattern <@USER_ID>
        mentions = re.findall(r"<@!?(\d+)>", embed.description)
        if mentions:
            user_id = int(mentions[0])
            return guild.get_member(user_id)

    # Check all fields
    for field in embed.fields:
        mentions = re.findall(r"<@!?(\d+)>", field.value)
        if mentions:
            user_id = int(mentions[0])
            member = guild.get_member(user_id)
            if member:
                return member

    # Check title
    if embed.title:
        mentions = re.findall(r"<@!?(\d+)>", embed.title)
        if mentions:
            user_id = int(mentions[0])
            return guild.get_member(user_id)

    return None
