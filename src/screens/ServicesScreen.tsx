import React from 'react';
import { View, ScrollView, StyleSheet, Platform } from 'react-native';
import { Appbar, Card, Text, useTheme } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { SafeAreaView } from 'react-native-safe-area-context';

export const ServicesScreen = () => {
  const { connectedDevice } = useBLE();
  const theme = useTheme();

  if (!connectedDevice) {
    return (
      <View style={styles.center}>
        <Text variant="headlineMedium" style={{ color: theme.colors.secondary, marginBottom: 8 }}>No device connected</Text>
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant }}>Please connect to a device from the Scan tab.</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Appbar.Header elevated>
        <Appbar.Content title="Services & Characteristics" />
      </Appbar.Header>

      <ScrollView contentContainerStyle={styles.content}>
        <Card mode="elevated" style={styles.card}>
          <Card.Content>
            <Text variant="titleMedium" style={{ marginBottom: 8 }}>Device Info</Text>
            <View style={styles.codeBlock}>
              <Text style={styles.json}>{JSON.stringify(connectedDevice, null, 2)}</Text>
            </View>
          </Card.Content>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  content: { padding: 16 },
  card: { marginBottom: 16 },
  codeBlock: {
    backgroundColor: '#f0f0f0',
    padding: 12,
    borderRadius: 8,
  },
  json: { 
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', 
    fontSize: 12,
    color: '#333'
  },
});
