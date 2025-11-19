# Developer Environment Setup

This guide covers setting up a fresh React Native development environment on macOS for both iOS and Android, specifically targeting physical devices connected via USB.

## 1. System Prerequisites (macOS)

Ensure your system tools are up to date.

### Homebrew & Basic Tools
If you haven't installed Homebrew:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install essential tools:
```bash
brew install node
brew install watchman
```

### Java Development Kit (JDK)
React Native (0.73+) requires **JDK 17**. We recommend Zulu OpenJDK.
```bash
brew tap homebrew/cask-versions
brew install --cask zulu@17
```
*Verify:* `javac -version` should output something like `openjdk 17.0.x`.

### Node.js
We use `.nvmrc` to enforce the Node version (v20+).
1. Install [nvm](https://github.com/nvm-sh/nvm).
2. In the project root, run:
   ```bash
   nvm install
   nvm use
   ```

---

## 2. iOS Setup (Physical Device)

### Software Requirements
* **Xcode**: Install the latest version from the Mac App Store (Minimum Xcode 15+ for iOS 17+).
* **CocoaPods**:
    ```bash
    sudo gem install cocoapods
    ```

### Physical Device Configuration
1. **Connect via USB**: Plug your iPhone into your Mac.
2. **Trust Computer**: Unlock your phone and tap "Trust" if prompted.
3. **Developer Mode** (iOS 16+):
    * Go to **Settings > Privacy & Security > Developer Mode**.
    * Enable it and restart your device.
4. **Xcode Signing**:
    * Open `ios/BLECLIApp.xcworkspace` in Xcode.
    * Select the project root in the left navigator.
    * Select the **BLECLIApp** target.
    * Go to the **Signing & Capabilities** tab.
    * **Team**: Select your personal Apple ID (or create one).
    * **Bundle Identifier**: You may need to change `org.reactjs.native.example.BLECLIApp` to something unique (e.g., `com.yourname.blecliapp`) to sign successfully with a free account.

### Bluetooth Permissions
The `Info.plist` is already configured with:
* `NSBluetoothAlwaysUsageDescription`
* `NSBluetoothPeripheralUsageDescription`

When you first run the app, you **must** allow Bluetooth access when the system prompt appears.

---

## 3. Android Setup (Physical Device)

### Software Requirements
* **Android Studio**: Download and install.
* **Android SDK**:
    * Open Android Studio -> Settings -> Languages & Frameworks -> Android SDK.
    * **SDK Platforms**: Ensure **Android 14.0 ("UpsideDownCake")** (API 34) is checked.
    * **SDK Tools**: Ensure **Android SDK Build-Tools**, **Android SDK Platform-Tools**, and **Android Emulator** are installed.
* **Environment Variables**:
    Add the following to your `~/.zshrc` or `~/.zshprofile`:
    ```bash
    export ANDROID_HOME=$HOME/Library/Android/sdk
    export PATH=$PATH:$ANDROID_HOME/emulator
    export PATH=$PATH:$ANDROID_HOME/platform-tools
    ```
    Run `source ~/.zshrc` to apply.

### Physical Device Configuration
1. **Enable Developer Options**:
    * Go to **Settings > About Phone**.
    * Tap **Build Number** 7 times until "You are now a developer" appears.
2. **Enable USB Debugging**:
    * Go to **Settings > System > Developer Options**.
    * Enable **USB debugging**.
3. **Connect via USB**: Plug your Android phone into your Mac.
4. **Verify Connection**:
    Run:
    ```bash
    adb devices
    ```
    You should see your device ID listed. If it says "unauthorized", check your phone screen to allow the computer.

### Bluetooth Permissions
The `AndroidManifest.xml` is configured for Android 12+ (API 31+) permissions:
* `BLUETOOTH_SCAN`
* `BLUETOOTH_CONNECT`
* `ACCESS_FINE_LOCATION` (Required for scanning on older Android versions)

The app handles runtime permission requests. Ensure you tap "Allow" for "Nearby Devices" and "Location" when prompted.

---

## 4. Building and Running

1. **Install Dependencies**:
    ```bash
    npm install
    ```

2. **Install iOS Pods**:
    ```bash
    cd ios && pod install && cd ..
    ```

3. **Start Metro Bundler**:
    Open a terminal and run:
    ```bash
    npm start
    ```

4. **Run on Device**:
    * **iOS**:
        ```bash
        # Ensure your phone is connected and unlocked
        npm run ios -- --device "Your iPhone Name"
        ```
        *Note: You can find your phone name in Settings > General > About > Name.*
        *Alternatively, run directly from Xcode by selecting your device as the run destination.*

    * **Android**:
        ```bash
        # Ensure 'adb devices' shows your device
        npm run android
        ```

## Troubleshooting

* **iOS Signing Issues**: Open `ios/BLECLIApp.xcworkspace` in Xcode and check the "Signing & Capabilities" tab for errors.
* **Android Build Failures**:
    ```bash
    cd android && ./gradlew clean && cd ..
    ```
* **Bluetooth Not Working**:
    * Check if Bluetooth is enabled on the phone.
    * Go to App Settings on the phone and verify permissions are granted.
    * Restart the Metro bundler (`npm start -- --reset-cache`).
