import gradio as gr
from deep_agent import agent 
import os
import re
import traceback
import uuid
import hashlib
import base64
os.makedirs("static", exist_ok=True)

with open("frontend/css/style.css") as f:
    css = f.read()
logo_path = os.path.join(os.getcwd(), "frontend/img/ic_logo.png")

def embed_image_base64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()
 
logo_b64 = embed_image_base64(logo_path)


def get_user_id(request: gr.Request) -> str:
    """
    Generate a unique user ID based on session or IP.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           
    
    In production, replace this with proper authentication:
    - OAuth tokens
    - Session cookies
    - Database user IDs
    """
    if request:
        session_hash = request.session_hash if hasattr(request, 'session_hash') else None
        if session_hash:
            return f"user_{session_hash}"
        
        client_ip = request.client.host if hasattr(request, 'client') else "unknown"
        return f"user_{hashlib.md5(client_ip.encode()).hexdigest()[:8]}"
    
    return f"user_{uuid.uuid4().hex[:8]}"

def cleanup_static_folder():
    """
    Delete all files in the static folder after response is processed.
    Keeps the folder itself but removes all HTML map files.
    """
    static_dir = "static"
    
    if not os.path.exists(static_dir):
        print("Static folder doesn't exist, nothing to clean")
        return
    
    deleted_count = 0
    error_count = 0
    
    try:
        for filename in os.listdir(static_dir):
            file_path = os.path.join(static_dir, filename)
            
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    print(f"✓ Deleted: {filename}")
                    deleted_count += 1
                except Exception as e:
                    print(f"✗ Error deleting {filename}: {e}")
                    error_count += 1
        
        print(f"Cleanup complete: {deleted_count} files deleted, {error_count} errors")
        
    except Exception as e:
        print(f"Error accessing static folder: {e}")




def process_delivery_query(query, user_session_id, request: gr.Request):
    """
    Process delivery queries with multi-user support.
    
    Each user has isolated memory and cannot access other users' data.
    """

    query = query.replace("⏳ Processing your request...", "").strip()

    
    # if not query.strip():
    #     return "<div style='color:#d32f2f; padding:20px; background:#ffebee; border-radius:8px; border-left:4px solid #d32f2f;'>Please enter a query</div>", None, user_session_id

    if not query.strip():
        return "<div style='color:#d32f2f; padding:20px; background:#ffebee; border-radius:8px; border-left:4px solid #d32f2f;'>Please enter a query</div>", None, user_session_id, "❌ Please enter a query"

    print("Query:",query)
    if query == "":
        return "<div style='color:#d32f2f; padding:20px; background:#ffebee; border-radius:8px; border-left:4px solid #d32f2f;'>Please enter a valid query with actual text</div>", None, user_session_id, "❌ Please enter a valid query with actual text"
    
    stripped_query = query.strip()
    if not any(c.isalnum() for c in stripped_query):
        return "<div style='color:#d32f2f; padding:20px; background:#ffebee; border-radius:8px; border-left:4px solid #d32f2f;'>Please enter a valid query with actual text</div>", None, user_session_id, "❌ Please enter a valid query with actual text"
    
    if len(stripped_query) < 2:
        return "<div style='color:#d32f2f; padding:20px; background:#ffebee; border-radius:8px; border-left:4px solid #d32f2f;'>Please enter a more detailed query</div>", None, user_session_id, "❌ Please enter a more detailed query"
    
    try:
        user_id = get_user_id(request)
        
        if not user_session_id:
            user_session_id = str(uuid.uuid4())
            print(f"NEW SESSION: User={user_id} | Thread={user_session_id}")
        else:
            print(f"CONTINUING SESSION: User={user_id} | Thread={user_session_id}")
        
        config = {
            "configurable": {
                "user_id": user_id,
                "thread_id": user_session_id
            }
        }
        
        result = agent.invoke(
            {"messages": [{"role": "user", "content": query}]},
            config=config
        )
        
        response_text = ""
        if isinstance(result, dict) and "messages" in result:
            for message in reversed(result["messages"]):
                if getattr(message, "type", None) == "ai" and getattr(message, "content", None):
                    response_text = message.content
                    break
        else:
            response_text = str(result)
        
        print("="*60)
        print(f"USER: {user_id} | THREAD: {user_session_id}")
        print("AGENT RESPONSE:")
        print(response_text)
        print("="*60)
        
        map_file_path = None
        map_url_pattern = r'/view-map/([^\s\)]+\.html)'
        map_match = re.search(map_url_pattern, response_text)

        if map_match:
            map_filename = map_match.group(1)
            map_file_path = os.path.join("static", map_filename)
        elif os.path.exists("static"):
            map_files = [
                f for f in os.listdir("static")
                if (
                    f.startswith("route_")
                    or f.startswith("traffic_")
                    or f.startswith("weather_")
                    or f.startswith("multi_route_")
                ) and f.endswith(".html")
            ]
            print(map_files)
            if map_files:
                map_files.sort(
                    key=lambda x: os.path.getmtime(os.path.join("static", x)),
                    reverse=True,
                )
                map_file_path = os.path.join("static", map_files[0])

        response_text = re.sub(map_url_pattern, '', response_text)
        response_text = re.sub(r'INTERACTIVE MAP:.*?\n', '', response_text)

        html_response = format_response(response_text)

        map_display = None
        if map_file_path and os.path.exists(map_file_path):
            with open(map_file_path, 'r', encoding='utf-8') as f:
                map_html = f.read()

            map_display = f"""
            <div style='width:100%; height:650px; border-radius:12px; overflow:hidden; 
                        box-shadow:0 4px 12px rgba(0,0,0,0.15); border:1px solid #e0e0e0;'>
                <iframe srcdoc='{map_html.replace("'", "&apos;")}' 
                        style='width:100%; height:100%; border:none;'>
                </iframe>
            </div>
            """

        cleanup_static_folder()

        # return html_response, map_display, user_session_id
        query = query.replace("⏳ Processing your request...", "").strip()
        return html_response, map_display, user_session_id, f"Response generated successfully for you query: {query}.\nCheck your results below."


    except Exception as e:
        traceback.print_exc()
        error_html = f"""
        <div style='padding:25px; background:#ffebee; border-left:5px solid #ef5350; 
                    border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1);'>
            <h3 style='color:#c62828; margin:0 0 15px 0; font-weight:600;'>Error Occurred</h3>
            <p style='margin:0; color:#b71c1c; line-height:1.6;'><strong>Details:</strong> {str(e)}</p>
        </div>
        """
        # return error_html, None, user_session_id
        return error_html, None, user_session_id, f"❌ Error: {str(e)}\n\nPlease try again or rephrase your query."


def format_response(text):
    """Format response text into structured HTML sections"""
    
    if not text or len(text.strip()) < 10:
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
    lines = text.split('\n')
    
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
        clean_text = text.replace("\n", "<br>")
        html += f"""
        <div style='padding:20px; background:#f5f5f5; border-radius:10px; line-height:1.8;'>
            {clean_text}
        </div>"""
    
    html += "</div>"
    return html

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
    
    card_html = f"""
    <div style='margin-bottom:20px; border-radius:10px; overflow:hidden; 
                box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left:4px solid {border_color};'>
        <div style='background:{color}; color:white; padding:15px; font-weight:600; font-size:1.1em;'>
            {title}
        </div>
        <div style='background:{bg_color}; padding:20px; line-height:1.8; color:#2e2e2e; border:1px solid #e0e0e0;'>
            {formatted_content}
        </div>
    </div>
    """
    return card_html


def clear_all(current_session):
    """Clear all outputs but preserve session for memory continuity"""
    return (
        "",
        "<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; border-radius:10px; min-height:300px; display:flex; align-items:center; justify-content:center;'><div><p style='font-size:1.1em;'>Your route details will appear here</p><p style='font-size:0.9em; margin-top:10px; color:#9e9e9e;'>Enter a query and click Send to get started</p></div></div>",
        "<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; border-radius:10px; min-height:600px; display:flex; align-items:center; justify-content:center;'><div><p style='font-size:1.1em;'>Interactive map will appear here</p><p style='font-size:0.9em; margin-top:10px; color:#9e9e9e;'>Plan a route to see the map</p></div></div>",
        current_session  # Keep the session to preserve conversation memory
    )



with gr.Blocks(
    theme=gr.themes.Soft(primary_hue="green", secondary_hue="emerald"),
    title="SparkDelivery - Intelligent Route Planning",
    css=css
) as demo:
    
    # State to store thread_id per user session
    user_session_state = gr.State(value=None)
    
    gr.HTML(f"""
    <div class='header'>
 
    <!-- LEFT: LOGO -->
    <div class='header-logo'>
        <img src="{logo_b64}" width="120">
    </div>
 
        <h1>
            SparkDelivery - Intelligent Route Planning
        </h1>
</div>
<div style='text-align: center;'>
 <p style='margin-top:20px; font-size:1.30em; opacity:0.92; color: white;'>
        Smart Route Planning with Live Weather and Traffic Insights
    </p>
 
    <p style='margin-top:5px; font-size:1.05em; opacity:0.85; color: white;'>
        Powered by SparkBrains 
    </p>
</div>
    """)


    with gr.Group(elem_classes=["how-to-container"]):
        gr.Markdown("### How to Use")
        gr.Markdown(
                    """
            - Plan a route between cities  
            - Add cargo details  
            - Optimize multi-stop routes  
            - Check traffic or weather conditions  
            - Ask about previously planned routes  
            - Save delivery preferences  
                    """,
                    elem_classes=["how-to-list"]
                )

    with gr.Group(elem_classes=["query-container"]):  # Main container
    # ---- Sub Group 1: Query Input Block ----
        with gr.Group(elem_classes=["query-form"]):
            with gr.Group(elem_classes=["query-text-block"]):
                gr.Markdown("### Query Input")
                
                query_input = gr.Textbox(
                    placeholder=(
                        "Examples:\n"
                        "• Plan route from Mumbai to Pune\n"
                        "• Route from Delhi to Jaipur with 500kg package\n"
                        "• What was my last route?\n"
                        "• Save preference: I prefer morning deliveries"
                    ),
                    lines=9,
                    show_label=False,
                    elem_classes=["input-box"]
                )

            with gr.Row():
                submit_btn = gr.Button("Send", variant="primary", size="lg", scale=1, elem_classes=["primary"])
                clear_btn = gr.Button("Clear", size="lg", scale=1)

        # ---- Sub Group 2: Quick Examples Block ----
        with gr.Group(elem_classes=["examples-block"]):
            gr.Markdown("### Quick Examples")

            gr.Examples(
                examples=[
                    "Plan route from Delhi to Chandigarh",
                    "Route from Mumbai to Pune with 200kg cargo",
                    "Optimize route from Delhi to Bhopal, Chandigarh, Rohtak, and Pune",
                    "What was my last route?",
                    "Save preference: I prefer morning deliveries",
                    "Traffic conditions Bhopal to Jaipur",
                    "Weather forecast for Mumbai next 24 hours",
                ],
                inputs=query_input,
            )



    gr.Markdown("---")
    
    gr.Markdown("## Results", elem_classes=["results-heading"])
    
    with gr.Row():
        with gr.Column(scale=2, elem_classes=["iframe-container"]):
            gr.Markdown("### Route Details", elem_classes=["route-heading"])
            output = gr.HTML(
                label="",
                show_label=False,
                value="""<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; 
                         border-radius:10px; min-height:300px; display:flex; align-items:center; 
                         justify-content:center;'>
                         <div><p style='font-size:1.1em;'>Your route details will appear here</p>
                         <p style='font-size:0.9em; margin-top:10px; color:#9e9e9e;'>
                         Enter a query and click Send to get started</p></div></div>"""
            )
        
        with gr.Column(scale=3):
            gr.Markdown("### Interactive Map", elem_classes=["route-heading"])
            map_output = gr.HTML(
                label="",
                show_label=False,
                value="""<div style='padding:40px; text-align:center; color:#757575; background:#fafafa; 
                         border-radius:10px; min-height:300px; display:flex; align-items:center; 
                         justify-content:center;'>
                         <div><p style='font-size:1.1em;'>Interactive map will appear here</p>
                         <p style='font-size:0.9em; margin-top:10px; color:#9e9e9e;'>
                         Plan a route to see the map</p></div></div>"""
            )
    

    def reset_before_new_query(query):
        """Show loading state in query input while processing"""
        loading_message = f"{query}\n\n⏳ Processing your request..."
        return loading_message


    submit_btn.click(
    fn=reset_before_new_query, 
    inputs=[query_input],  
    outputs=[query_input]  
    ).then(
        fn=process_delivery_query,
        inputs=[query_input, user_session_state],
        outputs=[output, map_output, user_session_state,query_input],
    )
    
    
    query_input.submit(
        fn=process_delivery_query,
        inputs=[query_input, user_session_state],
        outputs=[output, map_output, user_session_state,query_input]
    )
    

    clear_btn.click(
        fn=clear_all,
        inputs=[user_session_state],
        outputs=[query_input, output, map_output, user_session_state]
    )

    gr.Markdown("---")
    gr.Markdown(
        "<div style='text-align:center; color:#fff; font-size:0.9em; padding:20px 20px 0px 20px;'>"
        "Powered by DeepAgents | LangChain | Gemini | OpenStreetMap | OpenWeatherMap | TomTom<br>"
        "<span style='color:#78C841; font-size:0.85em; font-weight:600;'>Real-time routing with multi-user memory isolation</span>"
        "</div>"
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True
    )
