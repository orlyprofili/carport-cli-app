import React from 'react';
import { View, Text, Button, FlatList, TouchableOpacity, StyleSheet } from 'react-native';
import { useBLE } from '../context/BLEContext';
import { useNavigation } from '@react-navigation/native';

export const ScanScreen = () => {
  const { scan, stopScan, isScanning, devices, connect } = useBLE();
  const navigation = useNavigation();

  const handleConnect = async (id: string) => {
    await connect(id);
    navigation.navigate('CLI' as never);
  };

  const toggleScan = () => {
    if (isScanning) {
      stopScan();
    } else {
      scan();
    }
  };

  return (
    <View style={styles.container}>
      <Button title={isScanning ? 'Stop Scanning' : 'Scan'} onPress={toggleScan} />
      <FlatList
        data={devices}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <TouchableOpacity onPress={() => handleConnect(item.id)} style={styles.item}>
            <Text style={styles.name}>{item.name || 'Unnamed'}</Text>
            <Text style={styles.id}>{item.id}</Text>
            <Text>RSSI: {item.rssi}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20 },
  item: { padding: 10, borderBottomWidth: 1, borderBottomColor: '#ccc' },
  name: { fontWeight: 'bold', fontSize: 16 },
  id: { color: '#666' },
});
