import os
import re
import uuid
import hashlib
from common.log import logger


def get_user_id(request) -> str:
    """
    Generate a unique user ID based on session or IP.

    In production, replace this with proper authentication:
    - OAuth tokens
    - Session cookies
    - Database user IDs
    """
    try:
        logger.info("Generating user ID")
        if request:
            session_hash = request.session_hash if hasattr(request, 'session_hash') else None
            if session_hash:
                return f"user_{session_hash}"

            client_ip = request.client.host if hasattr(request, 'client') else "unknown"
            logger.info(f"Client IP: {client_ip}")
            return f"user_{hashlib.md5(client_ip.encode()).hexdigest()[:8]}"
        return f"user_{uuid.uuid4().hex[:8]}"
    except Exception as e:
        logger.error("Error generating user ID, Try after some time. If the error persists, contact support.")
        raise e


def cleanup_static_folder():
    """
    Delete all files in the static folder after response is processed.
    Keeps the folder itself but removes all HTML map files.
    """
    logger.info("Cleaning up static folder")
    static_dir = "static"

    if not os.path.exists(static_dir):
        logger.info("Static folder doesn't exist, nothing to clean")
        return

    deleted_count = 0
    error_count = 0

    try:
        for filename in os.listdir(static_dir):
            file_path = os.path.join(static_dir, filename)

            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted: {filename}")
                    deleted_count += 1
                except Exception as e:
                    logger.info(f"Error deleting {filename}: {e}")
                    error_count += 1

        logger.info(f"Cleanup complete: {deleted_count} files deleted, {error_count} errors")

    except Exception as e:
        logger.info(f"Error accessing static folder: {e}")


def check_valid_query(query: str, user_session_id: str) -> str:
    """
    Validate user query to ensure it is not empty or non-informative.
    Returns the cleaned query if valid, raises ValueError if invalid.
    """
    try:
        query = query.replace("Processing your request...", "").strip()

        if not query:
            logger.error(f"Empty query received for session: {user_session_id}")
            raise ValueError("Please enter a query")

        if not any(c.isalnum() for c in query):
            logger.error(f"Non-informative query received for session: {user_session_id}")
            raise ValueError("Please enter a valid query with actual text")

        if len(query) < 2:
            logger.error(f"Too short query received for session: {user_session_id}")
            raise ValueError("Please enter a more detailed query")

        return query

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Invalid query detected: {str(e)}")
        raise e


def processing_map_path(response_text: str):
    """
    Process the response text to extract map file path if available.
    Returns: (map_file_path, cleaned_response_text)
    """
    try:
        logger.info("Processing map path from response text.")
        map_file_path = None
        map_url_pattern = r'/view-map/([^\s\)]+\.html)'
        map_match = re.search(map_url_pattern, response_text)

        if map_match:
            logger.info("Map file found in response text.")
            map_filename = map_match.group(1)
            map_file_path = os.path.join("static", map_filename)
        elif os.path.exists("static"):
            logger.info("Searching for map files in static folder.")
            map_files = [
                f for f in os.listdir("static")
                if (
                           f.startswith("route_")
                           or f.startswith("traffic_")
                           or f.startswith("weather_")
                           or f.startswith("multi_route_")
                   ) and f.endswith(".html")
            ]
            logger.info(f"Map files found: {map_files}")
            if map_files:
                map_files.sort(
                    key=lambda x: os.path.getmtime(os.path.join("static", x)),
                    reverse=True,
                )
                map_file_path = os.path.join("static", map_files[0])

        response_text = re.sub(map_url_pattern, '', response_text)
        response_text = re.sub(r'INTERACTIVE MAP:.*?\n', '', response_text)

        return map_file_path, response_text

    except Exception as e:
        logger.error(f"Error processing map path: {str(e)}")
        raise e


def display_map_link(map_file_path: str):
    """
    Return the relative URL path to the map file for frontend consumption.
    The frontend will load this file directly via iframe src or fetch.

    Returns:
        str: URL path to the map file (e.g., "/static/route_123.html")
        None: If no map file exists
    """
    try:
        logger.info("Generating map file URL for frontend.")

        if map_file_path and os.path.exists(map_file_path):
            map_filename = os.path.basename(map_file_path)
            map_url = f"/static/{map_filename}"
            logger.info(f"Map URL generated: {map_url}")
            return map_url

        logger.info("No valid map file found.")
        return None
    except Exception as e:
        logger.error(f"Error generating map URL: {str(e)}")
        raise e


def format_response(response_text: str):
    """
    Format the response text into HTML for better display.
    """
    try:
        logger.info("Formatting response text into HTML.")
        if not response_text or len(response_text.strip()) < 10:
            return """<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; 
                             border-radius:10px; min-height:300px; display:flex; align-items:center; 
                             justify-content:center;'>
                             <div><p style='font-size:1.1em;'>No response received</p></div></div>"""

        sections = {
            'route': '',
            'multi_route': '',
            'weather': '',
            'traffic': '',
            'cost': '',
            'other': ''
        }

        current_section = 'other'
        lines = response_text.split('\n')

        for line in lines:
            line_upper = line.upper()
            if 'OPTIMAL MULTI-ROUTE' in line_upper or 'MULTI-DESTINATION' in line_upper:
                current_section = 'multi_route'
                continue
            elif 'ROUTE' in line_upper and ('SUMMARY' in line_upper or 'ANALYSIS' in line_upper):
                current_section = 'route'
                continue
            elif 'WEATHER' in line_upper and ('CONDITION' in line_upper or 'ANALYSIS' in line_upper):
                current_section = 'weather'
                continue
            elif 'TRAFFIC' in line_upper and 'ANALYSIS' in line_upper:
                current_section = 'traffic'
                continue
            elif 'COST' in line_upper and ('ESTIMATE' in line_upper or 'BREAKDOWN' in line_upper):
                current_section = 'cost'
                continue

            sections[current_section] += line + '\n'

        html = "<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;'>"

        cards_created = 0

        if sections['multi_route'].strip():
            html += create_card("Multi-Destination Route Plan", sections['multi_route'], "#FF6B35", "multi_route")
            cards_created += 1

        if sections['route'].strip():
            html += create_card("Route Information", sections['route'], "#78C841", "route")
            cards_created += 1

        if sections['traffic'].strip():
            html += create_card("Traffic Analysis", sections['traffic'], "#f57c00", "traffic")
            cards_created += 1

        if sections['weather'].strip():
            html += create_card("Weather Conditions", sections['weather'], "#6B8E23", "weather")
            cards_created += 1

        if sections['cost'].strip():
            html += create_card("Cost Estimate", sections['cost'], "#7b1fa2", "cost")
            cards_created += 1

        if cards_created == 0:
            clean_text = response_text
            clean_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', clean_text)
            clean_text = clean_text.replace("\n\n", "<br><br>")
            clean_text = clean_text.replace("\n", "<br>")
            html += f"<div style='padding:20px; background:#f5f5f5; border-radius:10px; line-height:1.8;'>{clean_text}</div>"

        html += "</div>"
        return html
    except Exception as e:
        logger.error(f"Error formatting response: {str(e)}")
        raise e


def create_card(title, content, color, card_type):
    """Create a styled card for each section"""

    formatted_content = content.strip()

    if not formatted_content or len(formatted_content) < 3:
        return ""

    formatted_content = formatted_content.replace('\n', '<br>')

    formatted_content = re.sub(
        r'(Distance:|Duration:|ETA:|Base Duration:|Adjusted ETA:|Temperature:|Traffic:|Cost:|Vehicle:|Origin:|Destination:|Current Traffic:|Traffic Factor:|Expected Delay:|Advice:|Recommended Vehicle:|Total Cost:|Weather Alerts?:|Condition:|Starting from:|Best visiting order:|Total Travel Time:|Route Details:|Optimization Summary:)',
        r'<strong>\1</strong>',
        formatted_content
    )

    if 'WARNING' in formatted_content.upper() or 'ALERT' in formatted_content.upper() or 'Heavy' in formatted_content:
        border_color = '#ef5350'
        bg_color = '#fff5f5'
    else:
        border_color = color
        bg_color = '#ffffff'

    card_html = f"<div style='margin-bottom:20px; border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left:4px solid {border_color};'><div style='background:{color}; color:white; padding:15px; font-weight:600; font-size:1.1em;'>{title}</div><div style='background:{bg_color}; padding:20px; line-height:1.8; color:#2e2e2e; border:1px solid #e0e0e0;'>{formatted_content}</div></div>"
    return card_html