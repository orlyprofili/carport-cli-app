# Glove CLI App

A robust React Native application designed for interacting with Glove devices via Bluetooth Low Energy (BLE). This tool serves as both a command-line interface wrapper and a mobile diagnostic tool for the Glove hardware ecosystem.

## 🚀 Features

- **BLE Device Scanning & Connection**: Seamlessly discover and connect to Glove peripherals.
- **Service & Characteristic Explorer**: Inspect GATT services and characteristics in real-time.
- **Cross-Platform**: Runs on both iOS and Android physical devices.
- **Type-Safe**: Built with TypeScript for reliability and maintainability.

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js** (v18+ recommended, managed via `nvm`)
- **Watchman** (for file watching)
- **Ruby** (for iOS dependency management)
- **JDK 17** (for Android builds)
- **Xcode** (for iOS) & **Android Studio** (for Android)

For a comprehensive guide on setting up your development environment, please strictly follow our [**SETUP.md**](./SETUP.md).

## 🛠 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd glove-cli-app
   ```

2. **Install JavaScript dependencies**
   ```bash
   npm install
   ```

3. **Install Ruby dependencies (iOS only)**
   This project uses a `Gemfile` to ensure all developers use the same version of CocoaPods.
   ```bash
   gem install bundler
   bundle install
   ```

4. **Install Native Pods (iOS only)**
   ```bash
   cd ios
   bundle exec pod install
   cd ..
   ```

## 🏃‍♂️ Running the App

### 1. Start Metro Bundler
The Metro bundler compiles the JavaScript code. Keep this terminal open.
```bash
npm start
```

### 2. Run on Device
**Note:** This app requires Bluetooth hardware support and is best tested on physical devices.

#### iOS
```bash
npm run ios
# Or specify a device
npm run ios -- --device "Your iPhone Name"
```

#### Android
```bash
npm run android
```

## 📂 Project Structure

```
├── src/
│   ├── context/       # React Contexts (e.g., BLE state)
│   ├── screens/       # UI Screens (Scan, Services, CLI)
│   └── utils/         # Helper functions and parsers
├── ios/               # Native iOS project files
├── android/           # Native Android project files
├── __tests__/         # Jest test suites
├── App.tsx            # Application entry point
```

## 🧹 Cleaning the Project

If you encounter build issues or unexpected caching behavior, try these cleaning steps:

### Android
```bash
cd android && ./gradlew clean && cd ..
```

### iOS
```bash
# Clean build folder
cd ios && xcodebuild -workspace BLECLIApp.xcworkspace -scheme BLECLIApp clean && cd ..

# Deep clean (removes Pods and DerivedData)
rm -rf ios/Pods ios/Podfile.lock ~/Library/Developer/Xcode/DerivedData/BLECLIApp-*
```

### Metro Bundler (JavaScript)
```bash
npm start -- --reset-cache
```

### Watchman (File Watcher)
If you encounter "Recrawled this watch" warnings or file change detection issues:
```bash
watchman watch-del-all
watchman shutdown-server
```

## 🤝 Contributing

1. Ensure you run the linter before pushing: `npm run lint`
2. Follow the existing code style and directory structure.
3. Open a Pull Request against the `main` branch.

## 📄 License

This project is proprietary software.
