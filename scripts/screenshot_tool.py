import argparse
import asyncio
import threading
import socketserver
import http.server
from pathlib import Path
from playwright.async_api import async_playwright

# Define the pages we want to screenshot
# Paths are relative to the repo root
PAGES = [
    {
        "name": "marketing_home",
        "path": "marketing_site/index.html",
        "width": 1920,
        "height": 1080
    },
    {
        "name": "scoreboard_home",
        "path": "apps/scoreboard/homeFixtures.html",
        "width": 1080,
        "height": 1920 # Portrait
    },
    {
        "name": "scoreboard_away",
        "path": "apps/scoreboard/awayFixtures.html",
        "width": 1080,
        "height": 1920 # Portrait
    },
    {
        "name": "league_men",
        "path": "apps/league/leagueOfLeagues-men.html",
        "width": 1080,
        "height": 1920
    },
    {
        "name": "league_women",
        "path": "apps/league/leagueOfLeagues-women.html",
        "width": 1080,
        "height": 1920
    }
]

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_server(root_dir):
    # Find a free port
    httpd = socketserver.TCPServer(("localhost", 0), QuietHandler)
    port = httpd.server_address[1]
    print(f"Starting local server at http://localhost:{port} serving {root_dir}")
    
    # Serve from the repo root
    # We need to change CWD for SimpleHTTPRequestHandler
    import os
    os.chdir(root_dir)
    
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return port

async def take_screenshots(output_dir: Path):
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Resolve repo root (assumes this script is in scripts/)
    repo_root = Path(__file__).parent.parent.resolve()
    
    # Start local server
    port = start_server(repo_root)
    base_url = f"http://localhost:{port}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        
        for page_config in PAGES:
            print(f"Capturing {page_config['name']}...")
            
            context = await browser.new_context(
                viewport={"width": page_config["width"], "height": page_config["height"]},
                device_scale_factor=2.0 # High DPI
            )
            page = await context.new_page()
            
            # Listen for console logs
            page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
            page.on("pageerror", lambda exc: print(f"BROWSER ERROR: {exc}"))
            
            # Use HTTP URL
            url = f"{base_url}/{page_config['path']}"
            response = await page.goto(url, wait_until="domcontentloaded")
            
            if response.status != 200:
                 print(f"Error loading {url}: Status {response.status}")
                 continue

            # Specific waits based on page type
            try:
                if "scoreboard" in page_config["name"]:
                    # Wait for fixtures to load
                    await page.wait_for_selector(".fixture, .no-fixtures-message", timeout=10000)
                elif "league" in page_config["name"]:
                    # Wait for table rows
                    await page.wait_for_selector(".table-row", timeout=10000)
                
                # Additional buffer for layout
                await page.wait_for_timeout(1000)
                
            except Exception as e:
                print(f"Warning: Timeout waiting for content on {page_config['name']}: {e}")

            output_file = output_dir / f"{page_config['name']}.png"
            await page.screenshot(path=output_file, full_page=True)
            print(f" - Saved to {output_file}")
            
            await context.close()
            
        await browser.close()

def main():
    parser = argparse.ArgumentParser(description="Capture high-res screenshots of SAHC pages.")
    parser.add_argument("--output", "-o", default="screenshots", help="Directory to save screenshots")
    args = parser.parse_args()
    
    output_path = Path(args.output)
    if not output_path.is_absolute():
         # Make relative to repo root if not absolute
         output_path = Path(__file__).parent.parent / output_path
         
    asyncio.run(take_screenshots(output_path))

if __name__ == "__main__":
    main()
