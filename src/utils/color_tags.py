"""
Custom color tags for logging
"""
import re
from colorama import Fore, Back, Style

class ColorTags:
    """Handle custom color tags in strings"""
    
    # Color mappings
    COLORS = {
        'red': Fore.RED,
        'green': Fore.GREEN,
        'yellow': Fore.YELLOW,
        'blue': Fore.BLUE,
        'magenta': Fore.MAGENTA,
        'cyan': Fore.CYAN,
        'white': Fore.WHITE,
        'black': Fore.BLACK,
        'bright_red': Fore.RED + Style.BRIGHT,
        'bright_green': Fore.GREEN + Style.BRIGHT,
        'bright_yellow': Fore.YELLOW + Style.BRIGHT,
        'bright_blue': Fore.BLUE + Style.BRIGHT,
        'bright_magenta': Fore.MAGENTA + Style.BRIGHT,
        'bright_cyan': Fore.CYAN + Style.BRIGHT,
    }
    
    BACKGROUNDS = {
        'bg_red': Back.RED,
        'bg_green': Back.GREEN,
        'bg_yellow': Back.YELLOW,
        'bg_blue': Back.BLUE,
        'bg_magenta': Back.MAGENTA,
        'bg_cyan': Back.CYAN,
        'bg_white': Back.WHITE,
        'bg_black': Back.BLACK,
    }
    
    STYLES = {
        'bold': Style.BRIGHT,
        'dim': Style.DIM,
        'normal': Style.NORMAL,
        'reset': Style.RESET_ALL,
    }
    
    @classmethod
    def apply_colors(cls, text: str) -> str:
        """
        Apply color tags to text
        
        Supports tags like:
        - [red]text[/red]
        - [blue]text[/blue]
        - [bold]text[/bold]
        - [bg_yellow]text[/bg_yellow]
        
        Args:
            text: Text with color tags
            
        Returns:
            Colored text with ANSI codes
        """
        # Pattern to match [color]text[/color]
        pattern = r'\[([a-z_]+)\](.*?)\[/\1\]'
        
        def replace_tag(match):
            tag = match.group(1)
            content = match.group(2)
            
            # Check if it's a color, background, or style
            if tag in cls.COLORS:
                return f"{cls.COLORS[tag]}{content}{Style.RESET_ALL}"
            elif tag in cls.BACKGROUNDS:
                return f"{cls.BACKGROUNDS[tag]}{content}{Style.RESET_ALL}"
            elif tag in cls.STYLES:
                return f"{cls.STYLES[tag]}{content}{Style.RESET_ALL}"
            else:
                # Unknown tag, return as-is
                return match.group(0)
        
        # Apply all color tags
        colored_text = re.sub(pattern, replace_tag, text)
        
        return colored_text

def colorize(text: str) -> str:
    """
    Convenience function to apply color tags
    
    Args:
        text: Text with color tags
        
    Returns:
        Colored text
    """
    return ColorTags.apply_colors(text)