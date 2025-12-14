# Required to parse arguments
import argparse
from datetime import datetime, timezone
from operator import itemgetter

# Required to create and mainpulate HTML file
import jinja2 
from titlecase import titlecase
 
# Required to encode image into HTML file
import base64 

# Function to encode cover.png image into HTML base64 format
def image_encode():
    import os
    if os.path.exists("./cover.png"):
        with open("./cover.png", "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return None


DATETIMESTR = ''.join(
    [ch for ch in datetime.now(timezone.utc).isoformat()[0:19] if ch.isdigit()])


def capitalize_title(ugly_title):
    if (all(ch.isupper() or not(ch.isalpha()) for ch in ugly_title) or
            all(ch.islower() or not(ch.isalpha()) for ch in ugly_title)):
        # Title is ugly, titlecase it
        return titlecase(ugly_title)
    else:
        return ugly_title


def capitalize_headings(highlights):
    for highlight in highlights:
        if highlight['note'] and highlight['note'].startswith('.h'):
            highlight['text'] = capitalize_title(highlight['text'])

# Function to load Jinja Template
def load_template():
    return jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath="./")).get_template("output.j2")

# Function to add break for each highlight
def fix_highlight_text(unfixed):
    return unfixed.replace('<BR>', '\n')

# Function to get color of highlight from .mrexpt
def get_color(color_code):
    return (str(hex(4294967295 + int(color_code) + 1))[4:])

# Function to remove duplicate highlights
def remove_duplicate_highlights(full_highlights):
    unique_highlights = []
    for full_highlight in full_highlights:
        if len(unique_highlights) > 0:
            if (unique_highlights[-1]['text'] == full_highlight['text'] and
                    unique_highlights[-1]['note'] == full_highlight['note']):
                continue
        unique_highlights.append(full_highlight)
    return unique_highlights


def parse_new_format(content):
    """Parse the new Moon Reader export format with #A*# separators"""
    highlights = []
    # Split by highlight separator #A@#
    entries = content.split('#A@#')
    
    for entry in entries:
        if not entry.strip() or '#A*#' not in entry:
            continue
            
        try:
            # Split by #A*# to get location and rest
            parts = entry.split('#A*#', 1)
            if len(parts) < 2:
                continue
                
            location_str = parts[0].strip()
            rest = parts[1]
            
            # Parse the fields
            fields = {}
            for marker in ['#A1#', '#A2#', '#A3#', '#A4#', '#A5#', '#A6#', '#A7#', '#A8#']:
                if marker in rest:
                    idx = rest.find(marker)
                    next_marker_idx = len(rest)
                    for next_marker in ['#A1#', '#A2#', '#A3#', '#A4#', '#A5#', '#A6#', '#A7#', '#A8#']:
                        if next_marker != marker and next_marker in rest[idx+4:]:
                            temp_idx = rest.find(next_marker, idx+4)
                            if temp_idx < next_marker_idx:
                                next_marker_idx = temp_idx
                    fields[marker] = rest[idx+4:next_marker_idx]
            
            # The number before #A*# appears to be the absolute location in the book
            absolute_location = 0
            if location_str.isdigit():
                absolute_location = int(location_str)
            
            # Extract chapter number (first field after #A*#)
            chapter_match = rest.split('#', 1)[0].strip()
            chapter = int(chapter_match) if chapter_match.isdigit() else 0
            
            # Extract location within chapter (A2 and A3)
            location_in_chapter = int(fields.get('#A2#', '0'))
            
            # Extract color
            color_code = fields.get('#A4#', '-256')
            
            # Extract text (A7) and note (A8)
            text = fields.get('#A7#', '').strip()
            note = fields.get('#A8#', '').strip()
            
            if text:  # Only add if there's actual text
                highlights.append({
                    'color': get_color(color_code),
                    'text': text,
                    'note': note,
                    # Use absolute location for better sorting
                    'location': absolute_location if absolute_location > 0 else (chapter * 1000000) + location_in_chapter,
                })
        except (ValueError, IndexError) as e:
            # Skip malformed entries
            continue
    
    return highlights


def parse_old_format(lines):
    """Parse the old Moon Reader export format with # line separators"""
    items = []
    current_item = []
    for line in lines:
        # A line with `#` starts a new item
        if line == '#':
            items.append(current_item)
            current_item = []
        else:
            # Each line is a field
            current_item.append(line)
    items.append(current_item)
    
    # The first item isn't a highlight, it's some obscure metadata, so drop it
    items = items[1:] if len(items) > 1 else items
    
    highlights = [
        {
            'color': get_color(item[8]),
            'text': fix_highlight_text(item[12]),
            'note': item[11],
            'location': (int(item[4]) * 1000000) + int(item[6]),
        }
        for item in items if len(item) > 12
    ]
    return highlights


def do_convert(mrexpt_filename, html_filename, debug=True, titlecap=True,
               book_name=None, author='Unknown'):
    
    with open(mrexpt_filename, 'r', encoding='utf-8') as mrexpt_file:
        content = mrexpt_file.read()
    
    # Detect format: new format has #A*# markers, old format has # on separate lines
    if '#A*#' in content:
        # New format
        highlights = parse_new_format(content)
        if book_name is None:
            # Try to extract book name from filename
            import os
            book_name = os.path.splitext(os.path.basename(mrexpt_filename))[0].replace('_', ' ').title()
    else:
        # Old format
        lines = content.splitlines()
        highlights = parse_old_format(lines)
        # Try to get book name from the old format data
        if book_name is None and len(lines) > 1:
            items = []
            current_item = []
            for line in lines:
                if line == '#':
                    items.append(current_item)
                    current_item = []
                else:
                    current_item.append(line)
            items.append(current_item)
            if len(items) > 1 and len(items[1]) > 2:
                book_name = items[1][1] or items[1][2]
    
    if book_name is None:
        book_name = "Exported Highlights"
    
    if debug:
        book_name = book_name + ' - ' + DATETIMESTR
    # The .mrexpt is ordered by note creation, so now that we have an approximate location sort by that
    highlights = remove_duplicate_highlights(
        sorted(highlights, key=itemgetter('location')))
    if titlecap:
        capitalize_headings(highlights)

    # Rendering highlights for Jinja file
    render_vars = {
        # 'book_name': book_name,
        'author': author,
        'highlights': highlights,
        # 'year': DATETIMESTR[:4],
    }
    
    # Add image only if cover.png exists
    image_data = image_encode()
    if image_data:
        render_vars['image'] = image_data
    # Writing HTML File
    with open(html_filename, 'w', encoding='utf-8') as html_file:
        html_file.write(load_template().render(render_vars))


def boolstr(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 'on', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'off', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

# Function for parsing arguments
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=str, help="input file")
    parser.add_argument("-d", "--debug", type=boolstr, default=True,
                        help="run in debug mode - unique file and book name")
    parser.add_argument("-t", "--titlecap", type=boolstr, default=True,
                        help="convert ALL CAPS headings to Title Cap")
    parser.add_argument("-a", "--author", type=str,
                        help="name of the author(s)",
                        default='Unknown')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    mrexpt_filename = args.input
    html_filename = mrexpt_filename.replace('mrexpt', 'html')
    if args.debug:
        html_filename = html_filename.replace(
            '.html', '-' + DATETIMESTR + '.html')

    do_convert(mrexpt_filename, html_filename, debug=args.debug, titlecap=args.titlecap, author=args.author)
