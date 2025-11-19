import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { BLEProvider } from './src/context/BLEContext';
import { ScanScreen } from './src/screens/ScanScreen';
import { CLIScreen } from './src/screens/CLIScreen';
import { ServicesScreen } from './src/screens/ServicesScreen';

const Tab = createBottomTabNavigator();

const App = () => {
  return (
    <SafeAreaProvider>
      <BLEProvider>
        <NavigationContainer>
          <Tab.Navigator>
            <Tab.Screen name="Scan" component={ScanScreen} />
            <Tab.Screen name="CLI" component={CLIScreen} />
            <Tab.Screen name="Services" component={ServicesScreen} />
          </Tab.Navigator>
        </NavigationContainer>
      </BLEProvider>
    </SafeAreaProvider>
  );
};

export default App;
