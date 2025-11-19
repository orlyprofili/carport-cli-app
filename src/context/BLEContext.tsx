import React, { createContext, useState, useEffect, useContext, useRef } from 'react';
import { NativeModules, Platform, PermissionsAndroid } from 'react-native';
import BleManager, { Peripheral } from 'react-native-ble-manager';
import { Buffer } from 'buffer';
import { LogParser } from '../utils/LogParser';

const BleManagerModule = NativeModules.BleManager;
// const bleManagerEmitter = new NativeEventEmitter(BleManagerModule);

// 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
const SERVICE_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E';
const RX_UUID = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'; // Write
const TX_UUID = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'; // Notify

interface BLEContextType {
  isScanning: boolean;
  devices: Peripheral[];
  connectedDevice: Peripheral | null;
  scan: () => void;
  stopScan: () => Promise<void>;
  connect: (id: string) => Promise<void>;
  disconnect: () => Promise<void>;
  sendMessage: (msg: string) => Promise<void>;
  cliOutput: string[];
  monitorOutput: string[];
  clearCliOutput: () => void;
  clearMonitorOutput: () => void;
}

const BLEContext = createContext<BLEContextType | undefined>(undefined);

export const BLEProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isScanning, setIsScanning] = useState(false);
  const [devices, setDevices] = useState<Peripheral[]>([]);
  const [connectedDevice, setConnectedDevice] = useState<Peripheral | null>(null);
  const [cliOutput, setCliOutput] = useState<string[]>([]);
  const [monitorOutput, setMonitorOutput] = useState<string[]>([]);

  const logParser = useRef(new LogParser(
    (text) => setCliOutput(prev => {
      const next = [...prev, text];
      return next.length > 1000 ? next.slice(next.length - 1000) : next;
    }),
    (text) => setMonitorOutput(prev => {
      const next = [...prev, text];
      return next.length > 1000 ? next.slice(next.length - 1000) : next;
    })
  )).current;

  useEffect(() => {
    BleManager.start({ showAlert: false })
      .then(() => console.log('BleManager initialized'))
      .catch((err) => console.error('BleManager init error:', err));

    const handleDiscoverPeripheral = (peripheral: Peripheral) => {
      console.log('Discovered:', peripheral.name || peripheral.id);
      
      // Filter by SERVICE_UUID
      const advertisedUUIDs = peripheral.advertising?.serviceUUIDs;
      const hasServiceUUID = advertisedUUIDs?.some(uuid => 
        uuid.toLowerCase() === SERVICE_UUID.toLowerCase()
      );

      if (!hasServiceUUID) {
        return;
      }

      setDevices((prev) => {
        if (!prev.find((p) => p.id === peripheral.id)) {
          return [...prev, peripheral];
        }
        return prev;
      });
    };

    const handleStopScan = () => {
      setIsScanning(false);
    };

    const handleUpdateValue = (data: any) => {
      const str = Buffer.from(data.value).toString();
      logParser.feed(str);
    };

    const handleDisconnectedPeripheral = (data: any) => {
      console.log('Disconnected from ' + data.peripheral);
      setConnectedDevice((prev) => {
        if (prev?.id === data.peripheral) {
          return null;
        }
        return prev;
      });
    };

    const handleUpdateState = (args: any) => {
      console.log('BleManager state:', args.state);
    };

    const listeners = [
      BleManager.onDiscoverPeripheral(handleDiscoverPeripheral),
      BleManager.onStopScan(handleStopScan),
      BleManager.onDidUpdateValueForCharacteristic(handleUpdateValue),
      BleManager.onDisconnectPeripheral(handleDisconnectedPeripheral),
      BleManager.onDidUpdateState(handleUpdateState),
    ];

    return () => {
      listeners.forEach((l) => l.remove());
    };
  }, []);

  const scan = async () => {
    if (Platform.OS === 'android' && Platform.Version >= 23) {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION
      );
      if (granted !== PermissionsAndroid.RESULTS.GRANTED) return;
    }
    
    if (Platform.OS === 'android' && Platform.Version >= 31) {
       const result = await PermissionsAndroid.requestMultiple([
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      ]);
      if (!result['android.permission.BLUETOOTH_SCAN'] || !result['android.permission.BLUETOOTH_CONNECT']) return;
    }

    setDevices([]);
    setIsScanning(true);
    BleManager.scan({ serviceUUIDs: [SERVICE_UUID], seconds: 5, allowDuplicates: true }).catch((err) => {
      console.error(err);
      setIsScanning(false);
    });
  };

  const stopScan = async () => {
    try {
      await BleManager.stopScan();
      setIsScanning(false);
    } catch (error) {
      console.error(error);
    }
  };

  const connect = async (id: string) => {
    try {
      await BleManager.connect(id);
      
      // Wait for connection to stabilize (common practice in BLE)
      await new Promise<void>(resolve => setTimeout(resolve, 900));

      const peripheral = await BleManager.retrieveServices(id);
      setConnectedDevice(peripheral);
      
      // Start notification
      await BleManager.startNotification(id, SERVICE_UUID, TX_UUID);
    } catch (error) {
      console.error(error);
    }
  };

  const disconnect = async () => {
    if (connectedDevice) {
      await BleManager.disconnect(connectedDevice.id);
      setConnectedDevice(null);
    }
  };

  const sendMessage = async (msg: string) => {
    if (!connectedDevice) return;

    // Normalize newlines and ensure CRLF termination, matching dashboard.py behavior
    let normalized = msg.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    if (!normalized.endsWith('\n')) {
      normalized += '\n';
    }
    const encoded = normalized.replace(/\n/g, '\r\n');

    const buffer = Buffer.from(encoded);
    const data = Array.from(buffer);
    try {
      await BleManager.write(connectedDevice.id, SERVICE_UUID, RX_UUID, data);
      setCliOutput(prev => [...prev, `> ${msg}\n`]);
    } catch (error) {
      console.error(error);
    }
  };

  const clearCliOutput = () => setCliOutput([]);
  const clearMonitorOutput = () => setMonitorOutput([]);

  return (
    <BLEContext.Provider value={{ 
      isScanning, 
      devices, 
      connectedDevice, 
      scan, 
      stopScan, 
      connect, 
      disconnect, 
      sendMessage, 
      cliOutput,
      monitorOutput,
      clearCliOutput,
      clearMonitorOutput
    }}>
      {children}
    </BLEContext.Provider>
  );
};

export const useBLE = () => {
  const context = useContext(BLEContext);
  if (!context) throw new Error('useBLE must be used within a BLEProvider');
  return context;
};
