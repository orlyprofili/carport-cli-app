import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { PaperProvider, MD3LightTheme } from 'react-native-paper';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import { BLEProvider } from './src/context/BLEContext';
import { ScanScreen } from './src/screens/ScanScreen';
import { CLIScreen } from './src/screens/CLIScreen';
import { ServicesScreen } from './src/screens/ServicesScreen';

const Tab = createBottomTabNavigator();

const theme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: '#006CFF', // Tech blue
    secondary: '#00B8D4', // Teal
  },
};

const screenOptions = ({ route }: { route: any }) => ({
  headerShown: false,
  tabBarIcon: ({ color, size }: { color: string, size: number }) => {
    let iconName;

    if (route.name === 'Scan') {
      iconName = 'bluetooth-audio';
    } else if (route.name === 'CLI') {
      iconName = 'console-line';
    } else if (route.name === 'Services') {
      iconName = 'format-list-bulleted-type';
    }

    return <MaterialCommunityIcons name={iconName || 'circle'} size={size} color={color} />;
  },
  tabBarActiveTintColor: theme.colors.primary,
  tabBarInactiveTintColor: 'gray',
});

const App = () => {
  return (
    <SafeAreaProvider>
      <PaperProvider theme={theme}>
        <BLEProvider>
          <NavigationContainer>
            <Tab.Navigator
              screenOptions={screenOptions}
            >
              <Tab.Screen name="Scan" component={ScanScreen} />
              <Tab.Screen name="CLI" component={CLIScreen} />
              <Tab.Screen name="Services" component={ServicesScreen} />
            </Tab.Navigator>
          </NavigationContainer>
        </BLEProvider>
      </PaperProvider>
    </SafeAreaProvider>
  );
};

export default App;
