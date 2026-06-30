from mcp.server.fastmcp import FastMCP, Context
import json
import os
import time
import asyncio
import logging
import subprocess
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from typing import Dict, Any, Optional
import sys
import win32gui
import win32ui
import win32con
import win32api
from PIL import Image
import io
import base64
import glob
import re

from bom import build_bom
from activity import append_activity
from fab import load_profile, find_profile, evaluate_dfm
from impedance import solve_width_for_impedance, microstrip_z0, stripline_z0
from decoupling import audit_decoupling
from signalrules import (load_profile as load_signal_profile,
                         find_profile as find_signal_profile,
                         list_profiles as list_signal_profiles,
                         build_rule_commands as build_signal_rule_commands)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG for more detailed logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler(str(Path(__file__).with_name('altium_mcp.log')))  # Also log to file
    ]
)
logger = logging.getLogger("AltiumMCPServer")

# Set MCP_DIR to the directory of the current Python file
MCP_DIR = Path(__file__).parent
CONFIG_FILE = MCP_DIR / "config.json"
DEFAULT_SCRIPT_PATH = MCP_DIR / "AltiumScript" / "Altium_API.PrjScr"

# Use a fixed exchange directory for request/response JSON files.
# Both the Python MCP server and the Altium DelphiScript need to independently
# resolve to the same directory. C:\Users\Public is writable by all users and
# exists on every Windows machine. This avoids fragile script-project-path
# resolution that breaks when Altium caches stale script projects.
EXCHANGE_DIR = Path("C:/Users/Public/altium_mcp")
EXCHANGE_DIR.mkdir(exist_ok=True)
REQUEST_FILE = EXCHANGE_DIR / "request.json"
RESPONSE_FILE = EXCHANGE_DIR / "response.json"
# Human-readable audit trail of board/design-modifying tool calls.
ACTIVITY_LOG = EXCHANGE_DIR / "mcp_activity.log"
# Fab-house capability profiles ship alongside the server.
FAB_PROFILES_DIR = Path(__file__).resolve().parent / "fab_profiles"
# High-speed signal (net-class) profiles ship alongside the server.
SIGNAL_PROFILES_DIR = Path(__file__).resolve().parent / "signal_profiles"

# Initialize FastMCP server
mcp = FastMCP("AltiumMCP", description="Altium integration through the Model Context Protocol")

class AltiumConfig:
    def __init__(self):
        self.altium_exe_path = ""
        self.script_path = str(DEFAULT_SCRIPT_PATH)
        self.load_config()
    
    def load_config(self):
        """Load configuration from file or create default if it doesn't exist"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.altium_exe_path = config.get("altium_exe_path", "")
                    self.script_path = config.get("script_path", str(DEFAULT_SCRIPT_PATH))
                logger.info(f"Loaded configuration from {CONFIG_FILE}")
            except Exception as e:
                logger.error(f"Error loading configuration: {e}")
                self._create_default_config()
        else:
            logger.info("No configuration file found, creating default")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create a default configuration file with improved Altium executable discovery"""
        
        # Try to find Altium directories dynamically
        altium_base_path = r"C:\Program Files\Altium"
        altium_exe_path = None
        
        if os.path.exists(altium_base_path):
            # Find all directories that match the pattern AD*
            ad_dirs = glob.glob(os.path.join(altium_base_path, "AD*"))
            
            if ad_dirs:
                # Sort directories by version number (extract the number after "AD")
                def get_version_number(dir_path):
                    match = re.search(r"AD(\d+)", os.path.basename(dir_path))
                    if match:
                        return int(match.group(1))
                    return 0
                
                # Sort directories by version number (highest first)
                ad_dirs.sort(key=get_version_number, reverse=True)
                
                # Try each directory until we find one with X2.EXE
                for ad_dir in ad_dirs:
                    potential_exe = os.path.join(ad_dir, "X2.EXE")
                    if os.path.exists(potential_exe):
                        altium_exe_path = potential_exe
                        break
        
        # Set the found path (or empty string if nothing found)
        self.altium_exe_path = altium_exe_path if altium_exe_path else ""
        
        # Save the configuration
        self.save_config()
    
    def save_config(self):
        """Save configuration to file"""
        config = {
            "altium_exe_path": self.altium_exe_path,
            "script_path": self.script_path
        }
        
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"Saved configuration to {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def verify_paths(self):
        """Verify that the paths in the configuration exist, prompt for input if they don't"""

        # Initialize variables
        root = None
        paths_verified = True
        
        # Check Altium executable
        if not self.altium_exe_path or not os.path.exists(self.altium_exe_path):
            paths_verified = False
            
            # Before prompting, try an automatic discovery
            altium_base_path = r"C:\Program Files\Altium"
            if os.path.exists(altium_base_path):
                logger.info(f"Attempting automatic discovery in {altium_base_path}")
                # Find all directories that match the pattern AD*
                ad_dirs = glob.glob(os.path.join(altium_base_path, "AD*"))
                
                if ad_dirs:
                    # Sort directories by version number (extract the number after "AD")
                    def get_version_number(dir_path):
                        match = re.search(r"AD(\d+)", os.path.basename(dir_path))
                        if match:
                            return int(match.group(1))
                        return 0
                    
                    # Sort directories by version number (highest first)
                    ad_dirs.sort(key=get_version_number, reverse=True)
                    
                    # Try each directory until we find one with X2.EXE
                    for ad_dir in ad_dirs:
                        potential_exe = os.path.join(ad_dir, "X2.EXE")
                        if os.path.exists(potential_exe):
                            self.altium_exe_path = potential_exe
                            logger.info(f"Automatically found Altium at: {self.altium_exe_path}")
                            print(f"Automatically found Altium at: {self.altium_exe_path}")
                            paths_verified = True
                            break
            
            # If automatic discovery failed, prompt for input
            if not self.altium_exe_path or not os.path.exists(self.altium_exe_path):
                if root is None:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()  # Hide the main window
                
                logger.info("Altium executable not found. Prompting user for selection...")
                print(f"Altium executable not found. Searched in:")
                print(f"  - Automatically scanned C:\\Program Files\\Altium\\AD*\\X2.EXE")
                print(f"  - Last known path: {self.altium_exe_path}")
                print("Please select the Altium X2.EXE file...")
                
                self.altium_exe_path = filedialog.askopenfilename(
                    title="Select Altium Executable",
                    filetypes=[("Executable files", "*.exe")],  # Only allow .exe files
                    initialdir="C:/Program Files/Altium"
                )
                
                if not self.altium_exe_path:
                    logger.error("No Altium executable selected. Some functionality may not work.")
                    print("Warning: No Altium executable selected. Automatic script execution will be disabled.")
                    paths_verified = False
        
        # Check script path
        if not os.path.exists(self.script_path):
            paths_verified = False
            
            if root is None:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()  # Hide the main window
            
            logger.info(f"Script file not found at {self.script_path}. Prompting user for selection...")
            print(f"Script file not found at {self.script_path}. Please select the Altium project file...")
            
            selected_path = filedialog.askopenfilename(
                title="Select Altium Project File",
                filetypes=[("Altium Project files", "*.PrjScr")],  # Changed to PrjScr for script project
                initialdir=str(MCP_DIR)
            )
            
            if selected_path:
                self.script_path = selected_path
            else:
                logger.error("No script file selected. Some functionality may not work.")
                print("Warning: No script file selected. Please make sure to create one.")
                paths_verified = False
        
        # Clean up tkinter root if created
        if root is not None:
            root.destroy()
        
        # Save the updated configuration
        self.save_config()
        
        return paths_verified

class AltiumBridge:
    def __init__(self):
        # Ensure the MCP directory exists
        MCP_DIR.mkdir(exist_ok=True)
        
        # Load configuration
        self.config = AltiumConfig()
        self.config.verify_paths()
    
    async def execute_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a command in Altium via the bridge script"""
        try:
            # Clean up any existing response file
            if RESPONSE_FILE.exists():
                RESPONSE_FILE.unlink()
            
            # Write the request file with command and parameters
            with open(REQUEST_FILE, "w") as f:
                json.dump({
                    "command": command,
                    **params  # Include parameters directly in the main JSON object
                }, f, indent=2)
            
            logger.info(f"Wrote request file for command: {command}")
            
            # Run the Altium script
            success = await self.run_altium_script()
            if not success:
                return {"success": False, "error": "Failed to run Altium script"}
            
            # Wait for the response file
            logger.info(f"Waiting for response file to appear...")
            timeout = 120  # seconds
            start_time = time.time()
            while not RESPONSE_FILE.exists() and time.time() - start_time < timeout:
                await asyncio.sleep(0.5)
            
            if not RESPONSE_FILE.exists():
                logger.error("Timeout waiting for response from Altium")
                return {"success": False, "error": "No response received from Altium (timeout)"}
            
            # Read the response file and print it for debugging
            logger.info("Response file found, reading response")
            response_text = ""
            with open(RESPONSE_FILE, "r") as f:
                response_text = f.read()
            
            # Log the raw response for debugging
            logger.info(f"Raw response (first 200 chars): {response_text[:200]}")
            
            # Parse the JSON response with detailed error handling
            try:
                response = json.loads(response_text)
                logger.info(f"Successfully parsed JSON response")
                append_activity(ACTIVITY_LOG, command, params, response)
                return response
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON response: {e}")
                logger.error(f"Error at position {e.pos}, line {e.lineno}, column {e.colno}")
                logger.error(f"Character at error position: '{response_text[e.pos:e.pos+10]}...'")
                
                # Try to manually fix common JSON issues
                logger.info("Attempting to fix JSON response...")
                fixed_text = response_text
                
                # Fix 1: If there's a quoted JSON array, try to fix it
                if '"[' in fixed_text and ']"' in fixed_text:
                    fixed_text = fixed_text.replace('"[', '[').replace(']"', ']')
                    logger.info("Fixed double-quoted JSON array")
                
                # Fix 2: Handle escaped quotes in JSON strings
                fixed_text = fixed_text.replace('\\"', '"')
                
                # Try to parse the fixed JSON
                try:
                    fixed_response = json.loads(fixed_text)
                    logger.info("Successfully parsed fixed JSON response")
                    return fixed_response
                except json.JSONDecodeError as e2:
                    logger.error(f"Still failed to parse JSON after fixes: {e2}")
                
                # If all else fails, return a structured error
                return {
                    "success": False, 
                    "error": f"Invalid JSON response: {e}",
                    "raw_response": response_text[:500]  # Include part of the raw response for diagnosis
                }
        
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _resolve_msix_path(virtual_path: str) -> str:
        """Resolve an MSIX-virtualized path to the real filesystem path.

        When Claude Desktop is installed via MSIX (the standard .exe installer
        on modern Windows), file paths are virtualized under AppData\\Roaming\\
        but the real files live at AppData\\Local\\Packages\\Claude_*\\
        LocalCache\\Roaming\\. Child processes of the MSIX app (like Python)
        can see the virtualized paths, but external apps (like Altium) cannot.
        This resolves the path so external processes can find the files.
        """
        appdata = os.environ.get('APPDATA', '')
        if not appdata or not virtual_path.startswith(appdata):
            return virtual_path

        localappdata = os.environ.get('LOCALAPPDATA', '')
        packages_dir = os.path.join(localappdata, 'Packages')
        if not os.path.isdir(packages_dir):
            return virtual_path

        try:
            for item in os.listdir(packages_dir):
                if item.startswith('Claude_'):
                    relative = os.path.relpath(virtual_path, appdata)
                    real_path = os.path.join(packages_dir, item, 'LocalCache', 'Roaming', relative)
                    if os.path.exists(real_path):
                        logger.info(f"Resolved MSIX path: {virtual_path} -> {real_path}")
                        return real_path
        except Exception as e:
            logger.warning(f"Error resolving MSIX path: {e}")

        return virtual_path

    async def run_altium_script(self) -> bool:
        """Run the Altium bridge script"""
        if not os.path.exists(self.config.altium_exe_path):
            logger.error(f"Altium executable not found at: {self.config.altium_exe_path}")
            print(f"Error: Altium executable not found. Please check the configuration.")
            return False

        if not os.path.exists(self.config.script_path):
            logger.error(f"Script file not found at: {self.config.script_path}")
            print(f"Error: Script file not found. Please check the configuration.")
            return False

        try:
            # Resolve MSIX-virtualized path so Altium (an external process
            # outside the MSIX sandbox) can find the script files
            script_path = self._resolve_msix_path(self.config.script_path)

            # Command format: "X2.EXE" -RScriptingSystem:RunScript(ProjectName="path\file.PrjScr"|ProcName="ModuleName>Run")
            command = f'"{self.config.altium_exe_path}" -RScriptingSystem:RunScript(ProjectName="{script_path}"^|ProcName="Altium_API>Run")'
            
            logger.info(f"Running command: {command}")
            
            # Start the process
            process = subprocess.Popen(command, shell=True)
            
            # Don't wait for completion - Altium will run the script and generate the response
            logger.info(f"Launched Altium with script, process ID: {process.pid}")
            return True
        
        except Exception as e:
            logger.error(f"Error launching Altium: {e}")
            return False

# Create a global bridge instance
altium_bridge = AltiumBridge()

@mcp.tool()
async def get_all_component_property_names(ctx: Context) -> str:
    """
    Get all available component property names (JSON keys) from all components
    
    Returns:
        str: JSON array with all unique property names
    """
    logger.info("Getting all component property names")
    
    # Execute the command in Altium to get component data
    response = await altium_bridge.execute_command(
        "get_all_component_data", 
        {}
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting component data: {error_msg}")
        return json.dumps({"error": f"Failed to get component data: {error_msg}"})
    
    # Get the component data
    components_data = response.get("result", [])
    
    if not components_data:
        logger.info("No component data found")
        return json.dumps({"error": "No component data found"})
    
    try:
        # Parse the data if it's a string
        if isinstance(components_data, str):
            components_list = json.loads(components_data)
        else:
            components_list = components_data
            
        # Extract all unique property names from all components
        property_names = set()
        for component in components_list:
            property_names.update(component.keys())
        
        # Convert set to sorted list for consistent output
        property_list = sorted(list(property_names))
        
        logger.info(f"Found {len(property_list)} unique property names")
        return json.dumps(property_list, indent=2)
    except Exception as e:
        logger.error(f"Error processing component data: {e}")
        return json.dumps({"error": f"Failed to process component data: {str(e)}"})

@mcp.tool()
async def get_component_property_values(ctx: Context, property_name: str) -> str:
    """
    Get values of a specific property for all components
    
    Args:
        property_name (str): The name of the property to get values for
    
    Returns:
        str: JSON array with objects containing designator and property value
    """
    logger.info(f"Getting values for property: {property_name}")
    
    # Execute the command in Altium to get component data
    response = await altium_bridge.execute_command(
        "get_all_component_data", 
        {}
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting component data: {error_msg}")
        return json.dumps({"error": f"Failed to get component data: {error_msg}"})
    
    # Get the component data
    components_data = response.get("result", [])
    
    if not components_data:
        logger.info("No component data found")
        return json.dumps({"error": "No component data found"})
    
    try:
        # Parse the data if it's a string
        if isinstance(components_data, str):
            components_list = json.loads(components_data)
        else:
            components_list = components_data
            
        # Extract the property values along with designators
        property_values = []
        for component in components_list:
            designator = component.get("designator")
            if designator and property_name in component:
                property_values.append({
                    "designator": designator,
                    "value": component.get(property_name)
                })
        
        logger.info(f"Found {len(property_values)} components with property '{property_name}'")
        return json.dumps(property_values, indent=2)
    except Exception as e:
        logger.error(f"Error processing component data: {e}")
        return json.dumps({"error": f"Failed to process component data: {str(e)}"})
    
@mcp.tool()
async def get_symbol_placement_rules(ctx: Context) -> str:
    """
    Get schematic symbol placement rules from a local configuration file
    
    Returns:
        str: JSON object with rules for placing pins on schematic symbols
    """
    logger.info("Getting symbol placement rules")
    
    # Define the rules file path in the MCP directory
    rules_file_path = MCP_DIR / "symbol_placement_rules.txt"
    
    # Check if the rules file exists
    if not rules_file_path.exists():
        logger.info("Symbol placement rules file not found, suggesting creation")
        
        # Default rules content
        default_rules = (
            "Only place pins on the left and right side of the symbol. "
            "Place power rail pins at the upper right, ground pins in the bottom left, "
            "no connect pins in the bottom right, inputs on the left, outputs on the right, "
            "and try to group other pins together by similar functionality (for example, SPI, I2C, RGMII, etc.). "
            "Always separate groups by 100mil gaps unless there is extra spacing, then space out groups equal distance from each other. "
        )
        
        # Create a helpful message for the user
        message = {
            "success": False,
            "error": f"Rules file not found at: {rules_file_path}",
            "message": f"Let the user know that they can optionally update the file {rules_file_path} with custom symbol placement rules. "
                      f"Suggested content: {default_rules}"
        }
        
        return json.dumps(message, indent=2)
    
    # Read the rules file if it exists
    try:
        with open(rules_file_path, "r") as f:
            rules_content = f.read()
        
        logger.info("Successfully read symbol placement rules file")
        
        # Return the rules with a message about how to modify them
        result = {
            "success": True,
            "message": f"Modify {rules_file_path} with custom symbol placement instructions",
            "rules": rules_content
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error reading symbol placement rules file: {e}")
        return json.dumps({
            "success": False,
            "error": f"Failed to read rules file: {str(e)}"
        }, indent=2)

@mcp.tool()
async def get_library_symbol_reference(ctx: Context) -> str:
    """
    Get the currently open symbol from a schematic library to use as reference for creating a new symbol.
    This tool should be used before creating a new symbol to understand the structure of existing symbols.
    
    Returns:
        str: JSON object with the reference symbol data including pins, their types, positions, and orientations
    """
    logger.info("Getting library symbol reference data")
    
    # Execute the command in Altium to get symbol reference data
    response = await altium_bridge.execute_command(
        "get_library_symbol_reference", 
        {}
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting symbol reference: {error_msg}")
        return json.dumps({"error": f"Failed to get symbol reference: {error_msg}"})
    
    # Get the symbol reference data
    symbol_data = response.get("result", {})
    
    if not symbol_data:
        logger.info("No symbol reference data found")
        return json.dumps({"error": "No symbol reference data found or no symbol is currently selected in the library"})
    
    logger.info(f"Retrieved symbol reference data")
    return json.dumps(symbol_data, indent=2)

@mcp.tool()
async def search_library_symbol(ctx: Context, symbol_name: str, library_path: str = "") -> str:
    """
    Search for a symbol by name in a schematic library (.SchLib) and navigate to it.
    Supports partial name matching (case-insensitive). Returns all matches and navigates
    to the best match (exact match preferred, otherwise first partial match).

    This tool will automatically open the library file in Altium if a path is provided,
    so no SchLib needs to be open beforehand.

    Args:
        symbol_name (str): Name or partial name of the symbol to search for
        library_path (str): Full file path to the .SchLib file (e.g. "N:\\Libs\\Integrated_Circuits.SchLib").
                           The tool will open this file in Altium if it is not already open.
                           If empty, uses the currently open library.
                           If no library is open and no path is provided, ask the user for the file path.

    Returns:
        str: JSON object with search results including matches, navigated symbol, and full symbol list
    """
    logger.info(f"Searching for symbol: {symbol_name} in library: {library_path or '(current)'}")

    # Execute the command in Altium
    params = {"symbol_name": symbol_name}
    if library_path:
        params["library_path"] = library_path

    response = await altium_bridge.execute_command(
        "search_library_symbol",
        params
    )

    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error searching for symbol: {error_msg}")
        return json.dumps({"error": f"Failed to search for symbol: {error_msg}"})

    # Get the result data
    result = response.get("result", {})

    if not result:
        logger.info("No search results returned")
        return json.dumps({"error": "No results returned from symbol search"})

    logger.info(f"Symbol search complete. Found: {result.get('found', False)}")
    return json.dumps(result, indent=2)

@mcp.tool()
async def create_schematic_symbol(ctx: Context, symbol_name: str, description: str, pins: list, part_count: int = 1) -> str:
    """
    Before executing, run get_symbol_placement_rules first.
    Create a new schematic symbol in the current library with the specified pins
    Instructions: pins should be grouped together via function and only placed on
                  the left and right side in 100 mil increments

    Pin name inversion/overbar: To show an overbar on a pin name (for active-low signals),
                  place a backslash after EACH character that should be overbarred.
                  Examples: R\E\S\E\T\ renders as RESET with overbar.
                           C\S\/A0 renders as CS with overbar followed by /A0 without overbar.
                  Do NOT use ~{...} or other notation â€” only the backslash-per-character format works in Altium.

    Args:
        symbol_name (str): Name of the symbol to create
        description (str): Description of the schematic symbol
        pins (list): List of pin data in format ["pin_number|pin_name|pin_type|pin_orientation|x|y|owner_part_id", ...]
                    Pin types: eElectricHiZ, eElectricInput, eElectricIO, eElectricOpenCollector,
                               eElectricOpenEmitter, eElectricOutput, eElectricPassive, eElectricPower
                    Pin orientations: eRotate0 (right), eRotate90 (down), eRotate180 (left), eRotate270 (up)
                    X,Y coordinates in mils
                    owner_part_id (optional): Part number the pin belongs to (1-based).
                               Use 0 for pins shared across all parts (e.g. power/GND).
                               Defaults to 1 if omitted. Only needed for multi-part symbols.
        part_count (int): Number of parts in the symbol (default 1).
                         Use >1 for multi-part symbols like quad op-amps or hex buffers.

    Returns:
        str: JSON object with the result of the component creation
    """
    logger.info(f"Creating schematic symbol: {symbol_name} with {len(pins)} pins, {part_count} part(s)")

    # Execute the command in Altium to create a symbol with pins
    response = await altium_bridge.execute_command(
        "create_schematic_symbol",
        {
            "symbol_name": symbol_name,
            "description": description,
            "part_count": part_count,
            "pins": pins
        }
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating symbol: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to create symbol: {error_msg}"})
    
    # Get the result data
    result = response.get("result", {})
    
    logger.info(f"Symbol {symbol_name} created successfully with {len(pins)} pins")
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_schematic_data(ctx: Context, cmp_designators: list) -> str:
    """
    Get schematic data for components in Altium
    
    Args:
        cmp_designators (list): List of designators of the components (e.g., ["R1", "C5", "U3"])
    
    Returns:
        str: JSON object with schematic component data for requested designators
    """
    logger.info(f"Getting schematic data for components: {cmp_designators}")
    
    # Execute the command in Altium to get schematic data
    response = await altium_bridge.execute_command(
        "get_schematic_data",
        {}  # No parameters needed for this command in the Altium script
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting schematic data: {error_msg}")
        return json.dumps({"error": f"Failed to get schematic data: {error_msg}"})
    
    # Get the schematic data
    schematic_data = response.get("result", [])
    
    if not schematic_data:
        logger.info("No schematic data found")
        return json.dumps({"error": "No schematic data found"})
    
    try:
        # Parse the data if it's a string
        if isinstance(schematic_data, str):
            schematic_list = json.loads(schematic_data)
        else:
            schematic_list = schematic_data
        
        # Filter components by designator
        components = []
        missing_designators = []
        
        for designator in cmp_designators:
            found = False
            for component in schematic_list:
                if component.get("designator") == designator:
                    components.append(component)
                    found = True
                    break
            
            if not found:
                missing_designators.append(designator)
        
        result = {
            "components": components,
        }
        
        if missing_designators:
            result["missing_designators"] = missing_designators
            logger.info(f"Some designators not found in schematic data: {missing_designators}")
        
        logger.info(f"Found schematic data for {len(components)} components")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error processing schematic data: {e}")
        return json.dumps({"error": f"Failed to process schematic data: {str(e)}"})
    
@mcp.tool()
async def get_pcb_layers(ctx: Context) -> str:
    """
    Get detailed information about all layers in the current Altium PCB
    
    Returns:
        str: JSON object with detailed layer information including copper layers, 
             mechanical layers, and special layers with their properties
    """
    logger.info("Getting detailed PCB layer information")
    
    # Execute the command in Altium to get all layers data
    response = await altium_bridge.execute_command(
        "get_pcb_layers",
        {}  # No parameters needed
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting PCB layers: {error_msg}")
        return json.dumps({"error": f"Failed to get PCB layers: {error_msg}"})
    
    # Get the layers data
    layers_data = response.get("result", [])
    
    if not layers_data:
        logger.info("No PCB layers found")
        return json.dumps({"message": "No PCB layers found in the current document"})
    
    logger.info(f"Retrieved PCB layers data")
    return json.dumps(layers_data, indent=2)

@mcp.tool()
async def set_pcb_layer_visibility(ctx: Context, layer_names: list, visible: bool) -> str:
    """
    Set visibility for specified PCB layers
    
    Args:
        layer_names (list): List of layer names to modify (e.g., ["Top Layer", "Bottom Layer", "Mechanical 1"])
        visible (bool): Whether to show (True) or hide (False) the specified layers
        
    Returns:
        str: JSON object with the result of the operation
    """
    logger.info(f"Setting layers visibility: {layer_names} to {visible}")
    
    # Execute the command in Altium to set layer visibility
    response = await altium_bridge.execute_command(
        "set_pcb_layer_visibility",
        {
            "layer_names": layer_names,
            "visible": visible
        }
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error setting layer visibility: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to set layer visibility: {error_msg}"})
    
    # Get the result data
    result = response.get("result", {})
    
    logger.info(f"Layer visibility set successfully")
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_component_data(ctx: Context, cmp_designators: list) -> str:
    """
    Get all data for components in Altium
    
    Args:
        cmp_designators (list): List of designators of the components (e.g., ["R1", "C5", "U3"])
    
    Returns:
        str: JSON object with all component data for requested designators
    """
    logger.info(f"Getting data for components: {cmp_designators}")
    
    # Execute the command in Altium to get all component data
    response = await altium_bridge.execute_command(
        "get_all_component_data",
        {}  # No parameters needed for this command in the Altium script
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting component data: {error_msg}")
        return json.dumps({"error": f"Failed to get component data: {error_msg}"})
    
    # Get the component data
    component_data = response.get("result", [])
    
    if not component_data:
        logger.info("No component data found")
        return json.dumps({"error": "No component data found"})
    
    try:
        # Parse the data if it's a string
        if isinstance(component_data, str):
            component_list = json.loads(component_data)
        else:
            component_list = component_data
        
        # Filter components by designator
        components = []
        missing_designators = []
        
        for designator in cmp_designators:
            found = False
            for component in component_list:
                if component.get("designator") == designator:
                    components.append(component)
                    found = True
                    break
            
            if not found:
                missing_designators.append(designator)
        
        result = {
            "components": components,
        }
        
        if missing_designators:
            result["missing_designators"] = missing_designators
            logger.info(f"Some designators not found: {missing_designators}")
        
        logger.info(f"Found data for {len(components)} components")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error processing component data: {e}")
        return json.dumps({"error": f"Failed to process component data: {str(e)}"})

@mcp.tool()
async def get_selected_components_coordinates(ctx: Context) -> str:
    """
    Get coordinates and positioning information for selected components in Altium layout
    
    Returns:
        str: JSON array with positioning data (designator, x, y, rotation, width, height)
    """
    logger.info("Getting coordinates for selected components")
    
    # Execute the command in Altium to get selected components coordinates
    response = await altium_bridge.execute_command(
        "get_selected_components_coordinates",
        {}  # No parameters needed
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting selected components coordinates: {error_msg}")
        return json.dumps({"error": f"Failed to get selected components coordinates: {error_msg}"})
    
    # Get the components coordinates data
    components_coords = response.get("result", [])
    
    if not components_coords:
        logger.info("No selected components found")
        return json.dumps({"message": "No components are currently selected in the layout"})
    
    logger.info(f"Retrieved positioning data for selected components")
    return json.dumps(components_coords, indent=2)

@mcp.tool()
async def get_all_designators(ctx: Context) -> str:
    """
    Get all component designators from the current Altium board
    
    Returns:
        str: JSON array of all component designators on the current board
    """
    logger.info("Getting all component designators")
    
    # Execute the command in Altium to get all component data
    response = await altium_bridge.execute_command(
        "get_all_component_data",
        {}  # No parameters needed
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting component data: {error_msg}")
        return json.dumps({"error": f"Failed to get component data: {error_msg}"})
    
    # Get the component data
    component_data = response.get("result", [])
    
    if not component_data:
        logger.info("No component data found")
        return json.dumps({"error": "No component data found"})
    
    try:
        # Parse the data if it's a string
        if isinstance(component_data, str):
            component_list = json.loads(component_data)
        else:
            component_list = component_data
        
        # Extract designators
        designators = [comp.get("designator") for comp in component_list if "designator" in comp]
        
        logger.info(f"Found {len(designators)} designators")
        return json.dumps(designators)
    except Exception as e:
        logger.error(f"Error processing component data: {e}")
        return json.dumps({"error": f"Failed to process component data: {str(e)}"})

@mcp.tool()
async def get_component_pins(ctx: Context, cmp_designators: list) -> str:
    """
    Get pin data for components in Altium
    
    Args:
        cmp_designators (list): List of designators of the components (e.g., ["R1", "C5", "U3"])
    
    Returns:
        str: JSON object with pin data for requested designators
    """
    logger.info(f"Getting pin data for components: {cmp_designators}")
    
    # Execute the command in Altium to get pin data
    response = await altium_bridge.execute_command(
        "get_component_pins",
        {"designators": cmp_designators}  # Pass the list of designators
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting pin data: {error_msg}")
        return json.dumps({"error": f"Failed to get pin data: {error_msg}"})
    
    # Get the components pins data
    pins_data = response.get("result", [])
    
    if not pins_data:
        logger.info(f"No pin data found for designators: {cmp_designators}")
        return json.dumps({"message": "No pin data found for the specified components"})
    
    logger.info(f"Retrieved pin data for components")
    return json.dumps(pins_data, indent=2)

@mcp.tool()
async def get_all_nets(ctx: Context) -> str:
    """
    Return every unique net name in the active PCB document.

    Returns
    -------
    str :
        A JSON array of net names, e.g. ["GND", "VCC33", "USB_D+", ...]
    """
    logger.info("Getting all nets")

    response = await altium_bridge.execute_command("get_all_nets", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting nets: {error_msg}")
        return json.dumps({"error": f"Failed to get nets: {error_msg}"})

    # Result is already a JSONâ€‘serialisable Python list
    return json.dumps(response.get("result", []), indent=2)

@mcp.tool()
async def get_schematic_connectivity(ctx: Context) -> str:
    """
    Return pin-by-pin connectivity from the schematic, grouped by net name.

    Unlike get_schematic_nets (which returns only net names), this returns every
    component pin assigned to each net so you can see exactly what is connected
    where. Reads directly from the schematic source - not the PCB - so results
    are accurate even before the PCB has been updated from the schematic.

    Returns a JSON object keyed by net name. Each value is a list of pin
    references in DESIGNATOR-PIN format, e.g.:
    {
      "GND":  ["C1-2", "C2-2", "U1-8"],
      "3V3":  ["C1-1", "R1-1", "U2-VCC"]
    }
    """
    logger.info("Getting schematic connectivity")
    response = await altium_bridge.execute_command("get_schematic_connectivity", {})
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting schematic connectivity: {error_msg}")
        return json.dumps({"error": f"Failed to get schematic connectivity: {error_msg}"})
    return json.dumps(response.get("result", {}), indent=2)

@mcp.tool()
async def create_net_class(ctx: Context, class_name: str, net_names: list) -> str:
    """
    Create a new net class and add specified nets to it
    
    Args:
        class_name (str): Name of the net class to create or modify
        net_names (list): List of net names to add to the class
    
    Returns:
        str: JSON object with the result of the operation
    """
    logger.info(f"Creating net class '{class_name}' with {len(net_names)} nets")
    
    # Execute the command in Altium to create the net class
    response = await altium_bridge.execute_command(
        "create_net_class",
        {
            "class_name": class_name,
            "net_names": net_names
        }
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating net class: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to create net class: {error_msg}"})
    
    # Get the result data
    result = response.get("result", {})
    
    logger.info(f"Net class '{class_name}' created/modified successfully")
    return json.dumps(result, indent=2)
    
@mcp.tool()
async def set_component_position(ctx: Context, cmp_designator: str, x: float, y: float, rotation: float = -1) -> str:
    """
    Set a component's absolute position in the PCB layout
    
    Args:
        cmp_designator (str): Designator of the component to position (e.g., "R1", "C5", "U3")
        x (float): Absolute X position in mils
        y (float): Absolute Y position in mils
        rotation (float): Rotation angle in degrees (0-360), use -1 to keep current rotation
    
    Returns:
        str: JSON object with the result of the position operation
    """
    logger.info(f"Setting component {cmp_designator} position to X:{x}, Y:{y}, Rotation:{rotation}")
    
    response = await altium_bridge.execute_command(
        "set_component_position",
        {
            "designator": cmp_designator,
            "x": x,
            "y": y,
            "rotation": rotation
        }
    )
    
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error setting component position: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to set component position: {error_msg}"})
    
    result = response.get("result", {})
    logger.info(f"Component position set successfully")
    return json.dumps({"success": True, "result": result}, indent=2)

@mcp.tool()
async def move_components(ctx: Context, cmp_designators: list, x_offset: float, y_offset: float, rotation: float = 0) -> str:
    """
    Move components by RELATIVE offset from their current position (not absolute positioning)
    
    IMPORTANT: This moves components BY the offset amount, not TO a position.
    For absolute positioning, use set_component_position instead.
    
    Args:
        cmp_designators (list): List of designators of the components to move (e.g., ["R1", "C5", "U3"])
        x_offset (float): X offset distance in mils (positive = right, negative = left)
        y_offset (float): Y offset distance in mils (positive = up, negative = down)
        rotation (float): New absolute rotation angle in degrees (0-360), if 0 the rotation is not changed
    
    Returns:
        str: JSON object with the result of the move operation
    """
    logger.info(f"Moving components: {cmp_designators} by X:{x_offset}, Y:{y_offset}, Rotation:{rotation}")
    
    # Execute the command in Altium to move components
    response = await altium_bridge.execute_command(
        "move_components",
        {
            "designators": cmp_designators,
            "x_offset": x_offset,
            "y_offset": y_offset,
            "rotation": rotation
        }
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error moving components: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to move components: {error_msg}"})
    
    # Get the result data
    result = response.get("result", {})
    
    logger.info(f"Components moved successfully")
    return json.dumps({"success": True, "result": result}, indent=2)

@mcp.tool()
async def get_schematic_nets(ctx: Context) -> str:
    """
    Return every unique net name from all schematic documents in the active project.

    Unlike get_all_nets (which reads the PCB), this reads net labels and power
    symbols directly from the schematic source, so it works correctly even before
    the PCB has been updated from the schematic.

    Returns
    -------
    str :
        A JSON array of unique net names, e.g. ["GND", "VCC33", "USB_D+", ...]
    """
    logger.info("Getting all schematic nets")

    response = await altium_bridge.execute_command("get_schematic_nets", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting schematic nets: {error_msg}")
        return json.dumps({"error": f"Failed to get schematic nets: {error_msg}"})

    return json.dumps(response.get("result", []), indent=2)

@mcp.tool()
async def get_screenshot(ctx: Context, view_type: str = "pcb") -> str:
    """
    Take a screenshot of the Altium window
    
    Args:
        view_type (str): Type of view to capture - 'pcb' or 'sch'
    
    Returns:
        str: JSON object with screenshot data (base64 encoded) and metadata
    """
    logger.info(f"Taking screenshot of Altium {view_type} window")
    
    try:
        # First, execute the Altium command to ensure the right document type is focused
        response = await altium_bridge.execute_command(
            "take_view_screenshot", 
            {"view_type": view_type.lower()}
        )
        
        # Check for success
        if not response.get("success", False):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Error focusing {view_type} document: {error_msg}")
            return json.dumps({"success": False, "error": f"Failed to focus the correct document type: {error_msg}"})
        
        # Run the screenshot capture in a separate thread
        import threading
        import queue
        import datetime
        from PIL import Image
        
        result_queue = queue.Queue()
        
        def capture_screenshot_thread():
            try:
                # Find Altium windows
                altium_windows = []
                altium_fallback_windows = []
                
                def collect_altium_windows(hwnd, _):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        
                        # First, look for windows with Altium and .PrjPcb in the title
                        if "Altium" in title and ".PrjPcb" in title:
                            altium_windows.append({
                                "handle": hwnd,
                                "title": title,
                                "class_name": win32gui.GetClassName(hwnd),
                                "rect": win32gui.GetWindowRect(hwnd)
                            })
                        # Collect any window with Altium in the title as fallback
                        elif "Altium" in title:
                            altium_fallback_windows.append({
                                "handle": hwnd,
                                "title": title,
                                "class_name": win32gui.GetClassName(hwnd),
                                "rect": win32gui.GetWindowRect(hwnd)
                            })
                    return True
                
                win32gui.EnumWindows(collect_altium_windows, 0)
                
                # If no specific Altium .PrjPcb windows found, use the fallback
                if not altium_windows and altium_fallback_windows:
                    altium_windows = altium_fallback_windows
                
                if not altium_windows:
                    result_queue.put({
                        "success": False, 
                        "error": f"No Altium windows found for {view_type} view"
                    })
                    return
                
                # Use the first matching window
                window = altium_windows[0]
                hwnd = window["handle"]
                
                # Get window dimensions
                left, top, right, bottom = window["rect"]
                width = right - left
                height = bottom - top
                
                if width <= 0 or height <= 0:
                    result_queue.put({"success": False, "error": f"Invalid window dimensions: {width}x{height}"})
                    return
                
                # Try to activate the window
                try:
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Could not bring window to foreground: {e}")
                
                # Take screenshot using GDI functions instead of ImageGrab
                try:
                    # Get device context
                    hwndDC = win32gui.GetWindowDC(hwnd)
                    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
                    saveDC = mfcDC.CreateCompatibleDC()
                    
                    # Create a bitmap object
                    saveBitMap = win32ui.CreateBitmap()
                    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
                    saveDC.SelectObject(saveBitMap)
                    
                    # Copy the screen into the bitmap
                    saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
                    
                    # Convert the bitmap to an Image
                    bmpinfo = saveBitMap.GetInfo()
                    bmpstr = saveBitMap.GetBitmapBits(True)
                    img = Image.frombuffer(
                        'RGB',
                        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                        bmpstr, 'raw', 'BGRX', 0, 1)
                    
                    # Save a local copy of the screenshot for debugging (non-fatal if it fails)
                    try:
                        debug_filename = str(MCP_DIR / f"screenshot_{view_type}.png")
                        img.save(debug_filename)
                        logger.info(f"Saved debug screenshot to {debug_filename}")
                    except Exception as save_error:
                        logger.warning(f"Could not save debug screenshot to {debug_filename}: {save_error}")
                        debug_filename = None  # Clear it since save failed
                    
                    # Clean up GDI resources
                    win32gui.DeleteObject(saveBitMap.GetHandle())
                    saveDC.DeleteDC()
                    mfcDC.DeleteDC()
                    win32gui.ReleaseDC(hwnd, hwndDC)
                    
                    # Convert to base64
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    buffer.seek(0)
                    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
                    
                    # Put result in queue
                    result_queue.put({
                        "success": True,
                        "width": width,
                        "height": height,
                        "window_title": window["title"],
                        "window_class": window["class_name"],
                        "view_type": view_type,
                        "image_format": "PNG",
                        "encoding": "base64",
                        "debug_file": debug_filename,
                        "image_data": img_base64
                    })
                    
                except Exception as e:
                    import traceback
                    trace = traceback.format_exc()
                    logger.error(f"GDI screenshot error: {e}\n{trace}")
                    result_queue.put({
                        "success": False, 
                        "error": f"GDI screenshot failed: {str(e)}",
                        "traceback": trace
                    })
                
            except Exception as e:
                import traceback
                result_queue.put({
                    "success": False, 
                    "error": f"Screenshot thread error: {str(e)}",
                    "traceback": traceback.format_exc()
                })
        
        # Start the thread
        thread = threading.Thread(target=capture_screenshot_thread)
        thread.daemon = True
        thread.start()
        
        # Wait for the thread to complete
        thread.join(timeout=10)  # 10 second timeout
        
        if thread.is_alive():
            logger.error("Screenshot thread timed out")
            return json.dumps({"success": False, "error": "Screenshot operation timed out"})
        
        # Get the result from the queue
        if result_queue.empty():
            logger.error("Screenshot thread did not return a result")
            return json.dumps({"success": False, "error": "Screenshot thread did not return a result"})
        
        result = result_queue.get()
        
        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Screenshot error: {error_msg}")
            return json.dumps({"success": False, "error": error_msg})
        
        logger.info(f"Screenshot taken successfully, size: {result['width']}x{result['height']}")
        return json.dumps(result)
    
    except Exception as e:
        logger.error(f"Error in screenshot function: {str(e)}")
        return json.dumps({"success": False, "error": f"Failed to take screenshot: {str(e)}"})
    
@mcp.tool()
async def layout_duplicator(ctx: Context) -> str:
    """
    First step of layout duplication. Selects source components and returns data to match with destination components.
    
    Returns:
        str: JSON object with source and destination component data for matching
    """
    logger.info("Starting layout duplication - selection phase")
    
    # Execute the command in Altium to get component data
    response = await altium_bridge.execute_command(
        "layout_duplicator", 
        {}
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error in layout duplication selection: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to start layout duplication: {error_msg}"})
    
    # Get the component data
    components_data = response.get("result", {})
    
    if not components_data:
        logger.info("No component data found")
        return json.dumps({"success": False, "error": "No component data returned from Altium"})
    
    # Parse the result to check if no source components were selected
    try:
        if isinstance(components_data, str):
            result_json = json.loads(components_data)
            if not result_json.get("success", True):
                logger.info(f"Source component selection issue: {result_json.get('message', 'Unknown issue')}")
                return json.dumps(result_json)
    except Exception as e:
        logger.error(f"Error parsing layout duplicator result: {e}")
    
    logger.info(f"Retrieved layout duplicator component data")
    return json.dumps(components_data, indent=2)

@mcp.tool()
async def layout_duplicator_apply(ctx: Context, source_designators: list, destination_designators: list) -> str:
    """
    Second step of layout duplication. Applies the layout of source components to destination components.
    
    Args:
        source_designators (list): List of source component designators (e.g., ["R1", "C5", "U3"])
        destination_designators (list): List of destination component designators (e.g., ["R10", "C15", "U7"])
    
    Returns:
        str: JSON object with the result of the layout duplication
    """
    logger.info(f"Applying layout duplication from {source_designators} to {destination_designators}")
    
    # Execute the command in Altium to apply layout duplication
    response = await altium_bridge.execute_command(
        "layout_duplicator_apply",
        {
            "source_designators": source_designators,
            "destination_designators": destination_designators
        }
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error applying layout duplication: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to apply layout duplication: {error_msg}"})
    
    # Get the result data
    result = response.get("result", {})
    
    logger.info(f"Layout duplication applied successfully")
    return json.dumps(result, indent=2)
    
@mcp.tool()
async def get_pcb_rules(ctx: Context) -> str:
    """
    Get all design rules from the current Altium PCB
    
    Returns:
        str: JSON array of PCB design rules with their properties
    """
    logger.info("Getting PCB design rules")
    
    # Execute the command in Altium to get rule data
    response = await altium_bridge.execute_command(
        "get_pcb_rules",
        {}  # No parameters needed
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting PCB rules: {error_msg}")
        return json.dumps({"error": f"Failed to get PCB rules: {error_msg}"})
    
    # Get the rules data
    rules_data = response.get("result", [])
    
    if not rules_data:
        logger.info("No PCB rules found")
        return json.dumps({"message": "No PCB rules found in the current document"})
    
    logger.info(f"Retrieved PCB rules data")
    return json.dumps(rules_data, indent=2)

@mcp.tool()
async def create_via_rule(ctx: Context, rule_name: str,
                          pad_min_mils: float, pad_max_mils: float, pad_preferred_mils: float,
                          hole_min_mils: float, hole_max_mils: float, hole_preferred_mils: float,
                          scope1: str = "All") -> str:
    """
    Create a Routing Via Style design rule on the current Altium PCB, with
    independent min/max/preferred sizes for the via pad (outer diameter) and the
    hole (inner diameter).

    Use the min/max to encode the fabrication house's allowed range (e.g. the fab's
    minimum finished hole and minimum annular-ring-driven pad), and preferred to set
    the target size you want the autorouter / manual routing to use. All six values
    are written explicitly, so the rule never inherits Altium's default sizes.

    Args:
        rule_name: Name for the new rule.
        pad_min_mils: Minimum via pad (outer) diameter in mils.
        pad_max_mils: Maximum via pad diameter in mils.
        pad_preferred_mils: Preferred via pad diameter in mils.
        hole_min_mils: Minimum via hole (drill) diameter in mils.
        hole_max_mils: Maximum via hole diameter in mils.
        hole_preferred_mils: Preferred via hole diameter in mils.
        scope1: Scope as an Altium query (default "All", e.g. "InNet('GND')").

    Returns:
        str: JSON object with the created rule's details (or an error).
    """
    logger.info(f"Creating via rule {rule_name}")

    response = await altium_bridge.execute_command(
        "create_via_rule",
        {"rule_name": rule_name,
         "pad_min_mils": pad_min_mils, "pad_max_mils": pad_max_mils,
         "pad_preferred_mils": pad_preferred_mils,
         "hole_min_mils": hole_min_mils, "hole_max_mils": hole_max_mils,
         "hole_preferred_mils": hole_preferred_mils,
         "scope1": scope1},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating via rule: {error_msg}")
        return json.dumps({"error": f"Failed to create via rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def delete_design_rule(ctx: Context, rule_name: str) -> str:
    """
    Delete a single design rule from the current Altium PCB, matched by its exact
    name. Useful for cleaning up test or superseded rules.

    Args:
        rule_name: Exact name of the rule to delete (case-sensitive match).

    Returns:
        str: JSON object confirming the deleted rule (name + kind), or an error if
             no rule with that exact name exists.
    """
    logger.info(f"Deleting design rule {rule_name}")

    response = await altium_bridge.execute_command(
        "delete_design_rule", {"rule_name": rule_name}
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error deleting design rule: {error_msg}")
        return json.dumps({"error": f"Failed to delete design rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def update_width_rule(ctx: Context, rule_name: str, min_mils: float, max_mils: float,
                            preferred_mils: float) -> str:
    """
    Update an existing Width Constraint design rule, found by exact name, setting its
    per-layer min/max/preferred track widths across the whole layer stack. Use this to
    retune a high-speed net class's routing width without recreating the rule.

    Args:
        rule_name: Exact name of the existing Width Constraint rule to modify.
        min_mils: New minimum track width in mils.
        max_mils: New maximum track width in mils.
        preferred_mils: New preferred track width in mils.

    Returns:
        str: JSON object with the updated rule's details (or an error if the rule is
             missing or is not a Width Constraint).
    """
    logger.info(f"Updating width rule {rule_name}")

    response = await altium_bridge.execute_command(
        "update_width_rule",
        {"rule_name": rule_name, "min_mils": min_mils, "max_mils": max_mils,
         "preferred_mils": preferred_mils},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error updating width rule: {error_msg}")
        return json.dumps({"error": f"Failed to update width rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def create_diff_pair_rule(ctx: Context, rule_name: str, scope1: str, gap_mils: float,
                                min_width_mils: float, max_width_mils: float,
                                preferred_width_mils: float, max_uncoupled_mils: float) -> str:
    """
    Create a Differential Pairs Routing design rule on the current Altium PCB, scoped to
    a differential-pair class. Sets the intra-pair gap, the width window, and the maximum
    allowed uncoupled length.

    Args:
        rule_name: Name for the new rule.
        scope1: Scope query, e.g. "InDifferentialPairClass('USB_Lines')".
        gap_mils: Intra-pair gap target in mils.
        min_width_mils: Minimum trace width in mils.
        max_width_mils: Maximum trace width in mils.
        preferred_width_mils: Preferred trace width in mils.
        max_uncoupled_mils: Maximum uncoupled length in mils.

    Returns:
        str: JSON object with the created rule's details (or an error).
    """
    logger.info(f"Creating diff-pair rule {rule_name}")

    response = await altium_bridge.execute_command(
        "create_diff_pair_rule",
        {"rule_name": rule_name, "scope1": scope1, "gap_mils": gap_mils,
         "min_width_mils": min_width_mils, "max_width_mils": max_width_mils,
         "preferred_width_mils": preferred_width_mils,
         "max_uncoupled_mils": max_uncoupled_mils},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating diff-pair rule: {error_msg}")
        return json.dumps({"error": f"Failed to create diff-pair rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def create_impedance_rule(ctx: Context, rule_name: str, scope1: str,
                                min_ohms: float, max_ohms: float) -> str:
    """
    Create an Impedance Constraint design rule on the current Altium PCB, defining the
    allowed characteristic-impedance window (in ohms) for the scoped nets.

    Args:
        rule_name: Name for the new rule.
        scope1: Scope query, e.g. "InNetClass('USB')".
        min_ohms: Minimum allowed impedance in ohms.
        max_ohms: Maximum allowed impedance in ohms.

    Returns:
        str: JSON object with the created rule's details (or an error).
    """
    logger.info(f"Creating impedance rule {rule_name}")

    response = await altium_bridge.execute_command(
        "create_impedance_rule",
        {"rule_name": rule_name, "scope1": scope1,
         "min_ohms": min_ohms, "max_ohms": max_ohms},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating impedance rule: {error_msg}")
        return json.dumps({"error": f"Failed to create impedance rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def create_length_match_rule(ctx: Context, rule_name: str, scope1: str,
                                   tolerance_mils: float) -> str:
    """
    Create a Matched Net Lengths design rule on the current Altium PCB, defining the
    allowed length-matching tolerance (in mils) for the scoped net class.

    Args:
        rule_name: Name for the new rule.
        scope1: Scope query, e.g. "InNetClass('DDR_ADDR')".
        tolerance_mils: Allowed length mismatch in mils.

    Returns:
        str: JSON object with the created rule's details (or an error).
    """
    logger.info(f"Creating length-match rule {rule_name}")

    response = await altium_bridge.execute_command(
        "create_length_match_rule",
        {"rule_name": rule_name, "scope1": scope1, "tolerance_mils": tolerance_mils},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating length-match rule: {error_msg}")
        return json.dumps({"error": f"Failed to create length-match rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def apply_signal_profile(ctx: Context, net_class: str, profile: str) -> str:
    """
    Apply a high-speed signal profile to a net class: resolve the named profile
    (e.g. "usb2", "can") and create its width, differential-pair, impedance and
    matched-length design rules, all scoped to InNetClass('<net_class>'). Each rule
    is named after the net class (e.g. Width_<net_class>, DiffPair_<net_class>).

    This modifies the board (multiple rules). Use list_signal_profiles to see options.

    Args:
        net_class: Name of the target net class (must already exist on the board).
        profile: Signal profile name or file stem (e.g. "usb2", "can").

    Returns:
        str: JSON with each rule command's result (created / failed), and a summary.
    """
    logger.info(f"Applying signal profile {profile} to net class {net_class}")
    path = find_signal_profile(SIGNAL_PROFILES_DIR, profile)
    if path is None:
        return json.dumps({"error": f"No signal profile found for '{profile}'. "
                                    "Try list_signal_profiles."})
    try:
        prof = load_signal_profile(path)
    except Exception as exc:
        return json.dumps({"error": f"Invalid signal profile '{profile}': {exc}"})

    commands = build_signal_rule_commands(prof, net_class)
    results = []
    created = 0
    for cmd in commands:
        response = await altium_bridge.execute_command(cmd["command"], cmd["params"])
        ok = response.get("success", False)
        entry = {"command": cmd["command"],
                 "rule_name": cmd["params"].get("rule_name"),
                 "ok": ok}
        if ok:
            created += 1
            entry["result"] = response.get("result", {})
        else:
            entry["error"] = response.get("error", "Unknown error")
        results.append(entry)

    return json.dumps({
        "profile": prof.get("profile", profile),
        "net_class": net_class,
        "rules_attempted": len(commands),
        "rules_created": created,
        "all_succeeded": created == len(commands),
        "results": results,
    }, indent=2)


@mcp.tool()
async def list_signal_profiles(ctx: Context) -> str:
    """
    List the available high-speed signal profiles that ship with the server.

    Returns:
        str: JSON array of {profile, file} for each profile.
    """
    return json.dumps(list_signal_profiles(SIGNAL_PROFILES_DIR), indent=2)


@mcp.tool()
async def list_fab_profiles(ctx: Context) -> str:
    """
    List the available fab-house capability profiles that ship with the server.

    Returns:
        str: JSON array of {fab, file, verified} for each profile.
    """
    out = []
    for p in sorted(FAB_PROFILES_DIR.glob("*.json")):
        if p.name == "fab_profile.schema.json":
            continue
        try:
            data = load_profile(p)
            out.append({"fab": data.get("fab"), "file": p.name,
                        "verified": data.get("verified", False)})
        except Exception:
            out.append({"fab": None, "file": p.name, "verified": False})
    return json.dumps(out, indent=2)


@mcp.tool()
async def apply_fab_profile(ctx: Context, fab: str) -> str:
    """
    Apply a fab house's minimum capabilities to the current PCB's design rules. Tighten-only:
    raises the global min-width, min-clearance and routing-via floors to AT LEAST the fab's
    limits (never loosens a stricter existing rule), and ensures a Minimum Annular Ring rule
    exists. Use list_fab_profiles to see options.

    This modifies the board (one undoable step). It only touches All-scoped global rules;
    net-specific rules (impedance-controlled widths, diff pairs, power nets) are left untouched.
    Note: the fab minimum is a manufacturability floor, not a target - impedance- and
    current-driven widths are usually wider and should not be reduced to it.

    Args:
        fab: Fab name or profile file stem (e.g. "PCBWay").

    Returns:
        str: JSON with what was applied, or an error.
    """
    logger.info(f"Applying fab profile {fab}")
    path = find_profile(FAB_PROFILES_DIR, fab)
    if path is None:
        return json.dumps({"error": f"No fab profile found for '{fab}'. Try list_fab_profiles."})
    profile = load_profile(path)
    r = profile["rules"]
    response = await altium_bridge.execute_command("apply_fab_profile", {
        "min_trace_mm": r["min_trace_mm"],
        "min_space_mm": r["min_space_mm"],
        "via_hole_mm": r["min_via_drill_mm"],
        "via_pad_mm": r["min_via_diameter_mm"],
        "annular_mm": r["min_annular_ring_mm"],
    })
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        return json.dumps({"error": f"Failed to apply fab profile: {error_msg}"})
    result = response.get("result", {})
    result["fab"] = profile.get("fab")
    if not profile.get("verified", False):
        result["warning"] = ("Profile is UNVERIFIED - confirm these limits against the fab's "
                             "current published capabilities before relying on them.")
    return json.dumps(result, indent=2)


@mcp.tool()
async def check_against_fab(ctx: Context, fab: str) -> str:
    """
    DFM check: measure the current PCB and compare it against a fab house's minimum
    capabilities. Reports both rule-floor mismatches and actual geometry violations
    (smallest track, via hole/pad, annular ring, pad hole). Read-only.

    Args:
        fab: Fab name or profile file stem (e.g. "PCBWay").

    Returns:
        str: JSON with findings (each OK/VIOLATION, limit vs actual in mm + mil), a
             summary count, and the raw measurement.
    """
    logger.info(f"Checking board against fab {fab}")
    path = find_profile(FAB_PROFILES_DIR, fab)
    if path is None:
        return json.dumps({"error": f"No fab profile found for '{fab}'. Try list_fab_profiles."})
    profile = load_profile(path)
    response = await altium_bridge.execute_command("fab_measure", {})
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        return json.dumps({"error": f"Failed to measure board: {error_msg}"})
    measurement = response.get("result", {})
    report = evaluate_dfm(profile, measurement)
    report["measurement"] = measurement
    if not profile.get("verified", False):
        report["warning"] = ("Profile is UNVERIFIED - confirm these limits against the fab's "
                             "current published capabilities before relying on the result.")
    return json.dumps(report, indent=2)


@mcp.tool()
async def create_width_rule(ctx: Context, rule_name: str, min_mils: float, max_mils: float,
                            preferred_mils: float, scope1: str = "All") -> str:
    """
    Create a Width Constraint (routing width) design rule on the current Altium PCB.

    Args:
        rule_name: Name for the new rule.
        min_mils: Minimum track width in mils.
        max_mils: Maximum track width in mils.
        preferred_mils: Preferred track width in mils.
        scope1: Scope as an Altium query (default "All", e.g. "InNet('5V')").

    Returns:
        str: JSON object with the created rule's details (or an error).
    """
    logger.info(f"Creating width rule {rule_name}")

    response = await altium_bridge.execute_command(
        "create_width_rule",
        {"rule_name": rule_name, "min_mils": min_mils, "max_mils": max_mils,
         "preferred_mils": preferred_mils, "scope1": scope1},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating width rule: {error_msg}")
        return json.dumps({"error": f"Failed to create width rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def update_clearance_rule(ctx: Context, rule_name: str, gap_mils: float) -> str:
    """
    Update the gap of an existing Clearance Constraint design rule, found by name.

    Args:
        rule_name: Name of the existing clearance rule to modify.
        gap_mils: New minimum clearance gap in mils.

    Returns:
        str: JSON object with the updated rule's details (or an error).
    """
    logger.info(f"Updating clearance rule {rule_name}")

    response = await altium_bridge.execute_command(
        "update_clearance_rule", {"rule_name": rule_name, "gap_mils": gap_mils}
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error updating clearance rule: {error_msg}")
        return json.dumps({"error": f"Failed to update clearance rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def create_clearance_rule(ctx: Context, rule_name: str, gap_mils: float,
                                scope1: str = "All", scope2: str = "All") -> str:
    """
    Create a Clearance Constraint design rule on the current Altium PCB.

    Args:
        rule_name: Name for the new rule (e.g. "Clearance_HV").
        gap_mils: Minimum clearance gap in mils.
        scope1: First scope as an Altium query (default "All", e.g. "InNet('HV')").
        scope2: Second scope as an Altium query (default "All").

    Returns:
        str: JSON object with the created rule's details (or an error).
    """
    logger.info(f"Creating clearance rule {rule_name}")

    response = await altium_bridge.execute_command(
        "create_clearance_rule",
        {"rule_name": rule_name, "gap_mils": gap_mils, "scope1": scope1, "scope2": scope2},
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating clearance rule: {error_msg}")
        return json.dumps({"error": f"Failed to create clearance rule: {error_msg}"})

    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
async def run_drc(ctx: Context) -> str:
    """
    Run the batch Design Rule Check (DRC) on the current Altium PCB, then return the
    resulting violations, each with its name/description and location (x/y in mm and
    mils). Use this for an on-demand "check my board". The report window is suppressed.

    Note: repours all polygons first (a board modification, applied as a single
    undoable step) so the DRC is accurate and runs without Altium's repour prompt.
    For a non-modifying check, run the DRC manually in Altium and use
    get_drc_violations instead.

    Returns:
        str: JSON object with total_violations and a violations array
    """
    logger.info("Running DRC")

    response = await altium_bridge.execute_command("run_drc", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error running DRC: {error_msg}")
        return json.dumps({"error": f"Failed to run DRC: {error_msg}"})

    data = response.get("result", {})
    if not data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("DRC complete")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_drc_violations(ctx: Context) -> str:
    """
    Return the Design Rule Check (DRC) violations currently present on the active
    Altium PCB, each with its description and location (x/y in mm and mils) so you
    can find it on the board. Run a DRC in Altium first (Tools > Design Rule Check)
    to refresh the violation set.

    Returns:
        str: JSON object with total_violations and a violations array
    """
    logger.info("Getting DRC violations")

    response = await altium_bridge.execute_command("get_drc_violations", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting DRC violations: {error_msg}")
        return json.dumps({"error": f"Failed to get DRC violations: {error_msg}"})

    data = response.get("result", {})
    if not data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("DRC complete")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_bom(ctx: Context) -> str:
    """
    Export a grouped Bill of Materials (BOM) for the current Altium PCB.
    Components are grouped by (description, footprint); each line lists the
    quantity and the designators. Built from get_all_component_data.

    Returns:
        str: JSON object with total_components, total_lines, and a bom array
    """
    logger.info("Getting BOM")

    response = await altium_bridge.execute_command("get_all_component_data", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting component data for BOM: {error_msg}")
        return json.dumps({"error": f"Failed to get BOM: {error_msg}"})

    components = response.get("result", [])
    if isinstance(components, str):
        try:
            components = json.loads(components)
        except Exception:
            components = []

    logger.info("Built BOM")
    return json.dumps(build_bom(components), indent=2)


@mcp.tool()
async def get_nets_with_length(ctx: Context) -> str:
    """
    Get the total routed copper length (tracks + arcs) for every net that has
    routing on the current Altium PCB. Useful for length-matching review and
    signal-integrity sanity checks.

    Returns:
        str: JSON object with total_routed_nets and a nets array
             (each: net, length_mils, length_mm)
    """
    logger.info("Getting nets with length")

    response = await altium_bridge.execute_command("get_nets_with_length", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting nets with length: {error_msg}")
        return json.dumps({"error": f"Failed to get nets with length: {error_msg}"})

    data = response.get("result", {})
    if not data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("Retrieved nets with length")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_unrouted_nets(ctx: Context) -> str:
    """
    Get the nets that still have unrouted connections (outstanding ratsnest) on
    the current Altium PCB. Useful for routing-completion and bring-up review.

    NOTE: the underlying connectivity/ratsnest API is best-effort. The response
    includes a "connectivity_api_unconfirmed" flag indicating the result should
    be sanity-checked against Altium's own routed/unrouted indicators.

    Returns:
        str: JSON object with total_unrouted_nets and a nets array
             (each: net, unrouted_connections)
    """
    logger.info("Getting unrouted nets")

    response = await altium_bridge.execute_command("get_unrouted_nets", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting unrouted nets: {error_msg}")
        return json.dumps({"error": f"Failed to get unrouted nets: {error_msg}"})

    data = response.get("result", {})
    if not data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("Retrieved unrouted nets")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_net_continuity(ctx: Context, net_name: str = "") -> str:
    """
    Get the connected pads (as DESIGNATOR-PAD references) grouped by net on the
    current Altium PCB. Lets you see exactly what is physically connected to each
    net in the layout - useful for continuity/bring-up checks.

    Args:
        net_name (str): Optional. If provided, only that net is returned;
                        otherwise every net with pads is returned.

    Returns:
        str: JSON object with total_nets and a nets array
             (each: net, pad_count, pads[])
    """
    logger.info(f"Getting net continuity (net_name={net_name or '(all)'})")

    params = {}
    if net_name:
        params["net_name"] = net_name

    response = await altium_bridge.execute_command("get_net_continuity", params)

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting net continuity: {error_msg}")
        return json.dumps({"error": f"Failed to get net continuity: {error_msg}"})

    data = response.get("result", {})
    if not data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("Retrieved net continuity")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_testpoints(ctx: Context) -> str:
    """
    Get the pads and vias flagged as test points (fab and/or assembly side) on
    the current Altium PCB. Useful for bring-up and test-coverage review.

    NOTE: the testpoint flag property names are version-dependent; the response
    includes a "testpoint_property_unconfirmed" flag indicating the result
    should be sanity-checked against Altium's testpoint settings.

    Returns:
        str: JSON object with total_testpoints and a testpoints array
             (each: type, designator/net, testpoint_top, testpoint_bottom)
    """
    logger.info("Getting testpoints")

    response = await altium_bridge.execute_command("get_testpoints", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting testpoints: {error_msg}")
        return json.dumps({"error": f"Failed to get testpoints: {error_msg}"})

    data = response.get("result", {})
    if not data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("Retrieved testpoints")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_power_decoupling_audit(ctx: Context) -> str:
    """
    Audit decoupling/bypass capacitors per power-supply net on the current
    Altium PCB. For every net that looks like a power rail (e.g. 3V3, 1V8, +5V,
    VCC, VDD, VBAT, ...), lists the capacitors connected to it so you can spot
    under-bypassed rails during bring-up review.

    The grouping is done in pure Python (server/decoupling.py) from the component
    list (get_all_component_data) and per-net pad membership (get_net_continuity).

    Returns:
        str: JSON object with total_power_nets, total_decoupling_caps,
             undecoupled_power_nets, and a power_nets array
             (each: net, capacitor_count, capacitors[], decoupled)
    """
    logger.info("Getting power decoupling audit")

    # 1. Component list (for capacitor classification)
    comp_response = await altium_bridge.execute_command("get_all_component_data", {})
    if not comp_response.get("success", False):
        error_msg = comp_response.get("error", "Unknown error")
        logger.error(f"Error getting component data: {error_msg}")
        return json.dumps({"error": f"Failed to get component data: {error_msg}"})

    components_data = comp_response.get("result", [])
    if isinstance(components_data, str):
        try:
            components = json.loads(components_data)
        except json.JSONDecodeError:
            components = []
    else:
        components = components_data or []

    # 2. Per-net pad membership
    cont_response = await altium_bridge.execute_command("get_net_continuity", {})
    if not cont_response.get("success", False):
        error_msg = cont_response.get("error", "Unknown error")
        logger.error(f"Error getting net continuity: {error_msg}")
        return json.dumps({"error": f"Failed to get net continuity: {error_msg}"})

    continuity = cont_response.get("result", {})
    if isinstance(continuity, str):
        try:
            continuity = json.loads(continuity)
        except json.JSONDecodeError:
            continuity = {}

    # Flatten continuity nets array into {net: [pad refs]}
    net_pads = {}
    for entry in (continuity or {}).get("nets", []):
        net_pads[entry.get("net", "")] = entry.get("pads", [])

    logger.info("Built power decoupling audit")
    return json.dumps(audit_decoupling(components, net_pads), indent=2)


@mcp.tool()
async def get_board_info(ctx: Context) -> str:
    """
    Get board-level summary information for the current Altium PCB:
    board name, display unit, overall width/height, origin, signal layer
    count, and total physical stackup thickness (in mm and mils).

    Returns:
        str: JSON object with board-level information
    """
    logger.info("Getting board info")

    response = await altium_bridge.execute_command("get_board_info", {})

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting board info: {error_msg}")
        return json.dumps({"error": f"Failed to get board info: {error_msg}"})

    board_data = response.get("result", {})
    if not board_data:
        return json.dumps({"message": "No active PCB document"})

    logger.info("Retrieved board info")
    return json.dumps(board_data, indent=2)


@mcp.tool()
async def get_pcb_layer_stackup(ctx: Context) -> str:
    """
    Get the detailed layer stackup information from the current Altium PCB including
    copper thickness, dielectric materials, constants, and heights
    
    Returns:
        str: JSON object with detailed layer stackup information
    """
    logger.info("Getting PCB layer stackup information")
    
    # Execute the command in Altium to get layer stackup data
    response = await altium_bridge.execute_command(
        "get_pcb_layer_stackup",
        {}  # No parameters needed
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting PCB layer stackup: {error_msg}")
        return json.dumps({"error": f"Failed to get PCB layer stackup: {error_msg}"})
    
    # Get the stackup data
    stackup_data = response.get("result", {})
    
    if not stackup_data:
        logger.info("No PCB layer stackup found")
        return json.dumps({"message": "No PCB layer stackup found in the current document"})
    
    logger.info(f"Retrieved PCB layer stackup data")
    return json.dumps(stackup_data, indent=2)


@mcp.tool()
async def suggest_trace_width(ctx: Context, target_ohms: float,
                              dielectric_height_mm: float, dk: float,
                              copper_thickness_mm: float = 0.035,
                              mode: str = "microstrip") -> str:
    """
    Estimate the PCB trace width needed for a target single-ended characteristic
    impedance. PURE COMPUTE - does not touch Altium.

    Uses closed-form analytic models (Hammerstad-Jensen microstrip / IPC-2141A
    stripline) and a bisection solver. The result is an ESTIMATE, typically within
    ~+/-5-10% of a 2D field solver. ALWAYS confirm the width against a field solver
    (e.g. Polar SI9000, Saturn PCB) or your fab's controlled-impedance calculator
    before committing a controlled-impedance design.

    Args:
        target_ohms: Desired characteristic impedance (ohms), e.g. 50.
        dielectric_height_mm: Dielectric height (mm). For microstrip this is the
            trace-to-plane substrate height; for stripline it is the TOTAL
            plane-to-plane spacing (trace assumed centred).
        dk: Dielectric constant (relative permittivity / Dk) of the substrate.
        copper_thickness_mm: Finished copper thickness (mm). Default 0.035 (~1 oz).
        mode: "microstrip" (surface) or "stripline" (buried). Default "microstrip".

    Returns:
        str: JSON with the estimated width (mm + mil), a Z0 back-check at that width,
             the inputs used, and an ESTIMATE/confirm-with-field-solver caveat.
    """
    logger.info(f"suggest_trace_width target={target_ohms} mode={mode}")
    try:
        res = solve_width_for_impedance(
            target_ohms=float(target_ohms),
            h_mm=float(dielectric_height_mm),
            er=float(dk),
            t_mm=float(copper_thickness_mm),
            mode=mode,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)})

    out = {
        "mode": mode,
        "inputs": {
            "target_ohms": target_ohms,
            "dielectric_height_mm": dielectric_height_mm,
            "dk": dk,
            "copper_thickness_mm": copper_thickness_mm,
        },
        "width_mm": res["width_mm"],
        "width_mil": res["width_mil"],
        "z0_check_ohms": res["z0_check_ohms"],
        "converged": res["converged"],
        "estimate_only": True,
        "note": res["note"],
    }
    return json.dumps(out, indent=2)


def _parse_signal_layer_geometry(stackup: dict, signal_layer: str, mode: str) -> dict:
    """
    Pull the Dk and dielectric height for a named signal layer out of the
    get_pcb_layer_stackup JSON. Parses defensively.

    The DelphiScript GetPCBLayerStackup emits per copper layer (exact field names):
        layer_name, layer_id, material_type, copper_thickness_mils,
        copper_thickness_um, dielectric_type, dielectric_material,
        dielectric_height_mils, dielectric_height_um, dielectric_constant,
        layer_order
    Note: heights/thicknesses are reported in mils and um (NOT mm), so we convert.

    For microstrip we use the dielectric directly below the named copper layer.
    For stripline we sum the dielectric directly above and below the named layer
    (its total plane-to-plane substrate) and use the layer's own Dk.
    """
    layers = stackup.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("stackup JSON has no 'layers' array")

    want = str(signal_layer).strip().lower()
    idx = None
    for i, ly in enumerate(layers):
        if not isinstance(ly, dict):
            continue
        if str(ly.get("layer_name", "")).strip().lower() == want:
            idx = i
            break
    if idx is None:
        names = [ly.get("layer_name") for ly in layers if isinstance(ly, dict)]
        raise ValueError(f"signal layer {signal_layer!r} not found. Layers: {names}")

    def _um_to_mm(v):
        try:
            return float(v) / 1000.0
        except (TypeError, ValueError):
            return None

    def _diel_below(i):
        ly = layers[i]
        h = _um_to_mm(ly.get("dielectric_height_um"))
        if h is None or h <= 0:
            # fall back to mils field if um missing
            try:
                mils = float(ly.get("dielectric_height_mils"))
                h = mils * 0.0254 if mils > 0 else None
            except (TypeError, ValueError):
                h = None
        dk = ly.get("dielectric_constant")
        try:
            dk = float(dk)
        except (TypeError, ValueError):
            dk = None
        return h, dk

    sig = layers[idx]

    if mode.strip().lower() == "microstrip":
        h, dk = _diel_below(idx)
        if not h or not dk:
            raise ValueError(
                f"Layer {signal_layer!r} has no usable dielectric below it "
                f"(height_mm={h}, dk={dk}). For a top/bottom microstrip the signal "
                f"layer must sit on a dielectric above a reference plane.")
        return {"h_mm": h, "dk": dk}

    # stripline: dielectric above (the layer above this one's 'below' gap) + below
    h_below, dk_below = _diel_below(idx)
    h_above, dk_above = (None, None)
    if idx > 0:
        h_above, dk_above = _diel_below(idx - 1)
    parts = [v for v in (h_above, h_below) if v]
    if not parts:
        raise ValueError(
            f"Layer {signal_layer!r}: could not find dielectric on either side for a "
            f"stripline. Heights above={h_above}, below={h_below}.")
    h_total = sum(parts)
    # Prefer the signal layer's own Dk, else whatever side reported one.
    dk = dk_below or dk_above
    if not dk:
        raise ValueError(f"Layer {signal_layer!r}: no dielectric_constant available.")
    return {"h_mm": h_total, "dk": dk}


@mcp.tool()
async def estimate_impedance_width_from_stackup(ctx: Context, target_ohms: float,
                                                signal_layer: str,
                                                mode: str = "microstrip") -> str:
    """
    Estimate the trace width for a target impedance using the ACTUAL board stack-up.

    Reads the current PCB layer stack-up from Altium (get_pcb_layer_stackup), pulls
    the dielectric height and Dk associated with the named signal layer, then solves
    for the width. The result is an ESTIMATE (analytic model, ~+/-5-10% vs a 2D field
    solver) - confirm it against a field solver or your fab's controlled-impedance
    calculator before use.

    Args:
        target_ohms: Desired characteristic impedance (ohms), e.g. 50.
        signal_layer: Copper layer name as it appears in the stack-up (e.g. "Top Layer").
        mode: "microstrip" (signal on a dielectric above one plane) or "stripline"
            (signal buried between two planes). Default "microstrip".

    Returns:
        str: JSON with the estimated width (mm + mil), the Dk/height taken from the
             stack-up, a Z0 back-check, and an ESTIMATE/confirm caveat.
    """
    logger.info(f"estimate_impedance_width_from_stackup layer={signal_layer} "
                f"target={target_ohms} mode={mode}")

    response = await altium_bridge.execute_command("get_pcb_layer_stackup", {})
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        return json.dumps({"error": f"Failed to get PCB layer stackup: {error_msg}"})

    stackup = response.get("result", {})
    if not isinstance(stackup, dict) or "error" in stackup:
        return json.dumps({"error": f"No usable stackup returned: {stackup}"})

    try:
        geo = _parse_signal_layer_geometry(stackup, signal_layer, mode)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    try:
        res = solve_width_for_impedance(
            target_ohms=float(target_ohms),
            h_mm=geo["h_mm"], er=geo["dk"], t_mm=0.035, mode=mode,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)})

    out = {
        "mode": mode,
        "signal_layer": signal_layer,
        "from_stackup": {
            "dielectric_height_mm": round(geo["h_mm"], 5),
            "dk": geo["dk"],
            "copper_thickness_mm_assumed": 0.035,
        },
        "width_mm": res["width_mm"],
        "width_mil": res["width_mil"],
        "z0_check_ohms": res["z0_check_ohms"],
        "converged": res["converged"],
        "estimate_only": True,
        "note": res["note"],
    }
    return json.dumps(out, indent=2)


@mcp.tool()
async def get_output_job_containers(ctx: Context) -> str:
    """
    Get all available output job containers from a specified OutJob file
    
    Args:
        outjob_path (str): Path to the OutJob file (optional, will use first open OutJob if not provided)
    
    Returns:
        str: JSON array with all output job containers and their properties
    """
    logger.info("Getting output job containers from the first open OutJob")
    
    # Execute the command in Altium to get output job containers
    response = await altium_bridge.execute_command(
        "get_output_job_containers", 
        {}  # No parameters needed - will use first open OutJob
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error getting output job containers: {error_msg}")
        return json.dumps({"error": f"Failed to get output job containers: {error_msg}"})
    
    # Get the containers data
    containers_data = response.get("result", [])
    
    if not containers_data:
        logger.info("No output job containers found")
        return json.dumps({"message": "No output job containers found"})
    
    logger.info(f"Retrieved output job containers data")
    return containers_data  # Already in JSON format

@mcp.tool()
async def run_output_jobs(ctx: Context, container_names: list) -> str:
    """
    Run specified output job containers
    
    Args:
        container_names (list): List of container names to run
    
    Returns:
        str: JSON object with results of running the output jobs
    """
    logger.info(f"Running output jobs")
    logger.info(f"Containers to run: {container_names}")
    
    # Execute the command in Altium to run output jobs
    response = await altium_bridge.execute_command(
        "run_output_jobs", 
        {"container_names": container_names}
    )
    
    # Check for success
    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error running output jobs: {error_msg}")
        return json.dumps({"error": f"Failed to run output jobs: {error_msg}"})
    
    # Get the result data
    result_data = response.get("result", {})
    
    logger.info(f"Output jobs execution completed")
    
    # If result_data is a string, it's already in JSON format
    if isinstance(result_data, str):
        return result_data
    
    # Otherwise, convert to JSON
    return json.dumps(result_data, indent=2)

@mcp.tool()
async def create_pcb_footprint(ctx: Context, footprint_name: str, description: str, pads: list, courtyard_x_mm: float = 0, courtyard_y_mm: float = 0) -> str:
    """
    Create a new PCB footprint in the currently active PcbLib document.
    The PcbLib (e.g. Discrete.PcbLib) must be the focused document in Altium.

    Pad format: each element is "pad_number|x_mm|y_mm|width_mm|height_mm|shape"
                shape options: Rect (default), Round, Oval
                Coordinates are in mm relative to component origin (0,0).
                Pin 1 is indicated by a gap in the top-left silkscreen corner.

    Courtyard & silkscreen are auto-generated from pad extents + 0.25 mm margin
    unless courtyard_x_mm / courtyard_y_mm are provided explicitly (half-dimensions).

    Args:
        footprint_name (str): Footprint name as it will appear in the library
        description (str): Description string
        pads (list): List of pad definitions, e.g. ["1|-0.9|0.55|1.0|0.8|Rect", ...]
        courtyard_x_mm (float): Half-width of courtyard in mm (0 = auto)
        courtyard_y_mm (float): Half-height of courtyard in mm (0 = auto)

    Returns:
        str: JSON object with result
    """
    logger.info(f"Creating PCB footprint: {footprint_name} with {len(pads)} pads")

    response = await altium_bridge.execute_command(
        "create_pcb_footprint",
        {
            "footprint_name": footprint_name,
            "description": description,
            "pads": pads,
            "courtyard_x_mm": courtyard_x_mm,
            "courtyard_y_mm": courtyard_y_mm,
        }
    )

    if not response.get("success", False):
        error_msg = response.get("error", "Unknown error")
        logger.error(f"Error creating footprint: {error_msg}")
        return json.dumps({"success": False, "error": f"Failed to create footprint: {error_msg}"})

    result = response.get("result", {})
    logger.info(f"Footprint {footprint_name} created successfully")
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_server_status(ctx: Context) -> str:
    """Get the current status of the Altium MCP server"""
    status = {
        "server": "Running",
        "altium_exe": altium_bridge.config.altium_exe_path,
        "script_path": altium_bridge.config.script_path,
        "altium_found": os.path.exists(altium_bridge.config.altium_exe_path),
        "script_found": os.path.exists(altium_bridge.config.script_path),
    }
    
    return json.dumps(status, indent=2)

if __name__ == "__main__":
    logger.info("Starting Altium MCP Server...")
    logger.info(f"Using MCP directory: {MCP_DIR}")
    
    # Initialize the directory
    MCP_DIR.mkdir(exist_ok=True)
    
    # Create the AltiumScript directory if it doesn't exist
    script_dir = MCP_DIR / "AltiumScript"
    script_dir.mkdir(exist_ok=True)
    
    # Verify configuration before starting
    if not altium_bridge.config.verify_paths():
        print("Warning: Configuration not complete. Some functionality may not work.")
    
    # Print status
    print(f"Altium executable: {altium_bridge.config.altium_exe_path}")
    print(f"Script path: {altium_bridge.config.script_path}")
    
    # Run the server
    mcp.run(transport='stdio')