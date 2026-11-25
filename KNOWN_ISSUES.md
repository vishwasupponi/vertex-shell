# Known Issues & Limitations


### App Runs in the Background Without Showing the GUI (Windows 10)
On certain Windows 10 builds, Vertex may launch as a background process without displaying the user interface. This is caused by the Windows **"Mark of the Web"** security feature blocking a required runtime library after download.

> **Status:** This issue has already been fixed internally and will be included in the next release alongside a few other minor bug fixes. Thank you for your patience!

In the meantime, you can resolve this manually using either of the two methods below:

#### Option 1: Unblock via File Properties (Recommended)
1. Open your Vertex installation folder and navigate to `Main\pythonnet\runtime\`.
2. Right-click **`Python.Runtime.dll`** and select **Properties**.
3. At the bottom of the **General** tab, check the **Unblock** box.
4. Click **Apply**, then **OK**.
5. Launch **`Vertex.exe`** again.

#### Option 2: Unblock via PowerShell
1. Open **PowerShell** in your Vertex installation directory (or open PowerShell and navigate to the folder).
2. Run the following command, replacing `"C:\Path\To\Vertex"` with the actual path to your Vertex folder:
   ```powershell
   Get-ChildItem -Path "C:\Path\To\Vertex" -Recurse | Unblock-File
