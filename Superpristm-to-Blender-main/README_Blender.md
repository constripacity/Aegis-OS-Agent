# SuperPrism Map Importer - Blender Addon

This addon allows you to import UberStrike Unity maps into Blender with a single click.

## Installation

### Method 1: Development (Quickest for you)
1. Open Blender.
2. Go to **Edit > Preferences > Add-ons**.
3. Click **Install...** (top right).
4. Navigate to your project folder: `C:\Users\Shadow\Desktop\Superpristm-to-Blender-main\blender\`.
5. Select **addon_superprism** (if it was zipped) or just run the scripts manually.
   *Actually, for development, the easiest way is:*
   1. Open the `Scripting` tab in Blender.
   2. Open `blender/addon_superprism/__init__.py`.
   3. Click **Run Script**.

### Method 2: Proper Addon Install
1. Zip the folder `blender/addon_superprism/`.
2. In Blender: **Edit > Preferences > Add-ons > Install**.
3. Select the `.zip` file.
4. Enable **SuperPrism Map Importer** in the list.

## Usage

1. Open the **3D Viewport**.
2. Press **N** on your keyboard to open the Sidebar.
3. Look for the **SuperPrism** tab.
4. Click **IMPORT MAP**.

## Features
- **Automatic Setup**: Clears scene, imports meshes, applies materials, builds hierarchy, and imports lights.
- **Smart Orientation**: Automatically fixes Unity -> Blender rotation (X90 Z180).
- **Material Preview**: Automatically switches the viewport to see textures instantly.
