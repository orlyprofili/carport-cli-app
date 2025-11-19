import React from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { useBLE } from '../context/BLEContext';

export const ServicesScreen = () => {
  const { connectedDevice } = useBLE();

  if (!connectedDevice) {
    return (
      <View style={styles.center}>
        <Text>No device connected</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.header}>Services & Characteristics</Text>
      <Text style={styles.json}>{JSON.stringify(connectedDevice, null, 2)}</Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { fontSize: 18, fontWeight: 'bold', marginBottom: 10 },
  json: { fontFamily: 'monospace', fontSize: 12 },
});
