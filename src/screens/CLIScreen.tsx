import React, { useState } from 'react';
import { View, Text, TextInput, Button, FlatList, StyleSheet } from 'react-native';
import { useBLE } from '../context/BLEContext';

export const CLIScreen = () => {
  const { connectedDevice, sendMessage, logs, disconnect } = useBLE();
  const [input, setInput] = useState('');

  if (!connectedDevice) {
    return (
      <View style={styles.center}>
        <Text>No device connected</Text>
      </View>
    );
  }

  const handleSend = () => {
    sendMessage(input);
    setInput('');
  };

  return (
    <View style={styles.container}>
      <Text style={styles.header}>Connected to: {connectedDevice.name}</Text>
      <Button title="Disconnect" onPress={disconnect} color="red" />
      <FlatList
        data={logs}
        keyExtractor={(_, i) => i.toString()}
        renderItem={({ item }) => <Text style={styles.log}>{item}</Text>}
        style={styles.logs}
      />
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Enter command"
        />
        <Button title="Send" onPress={handleSend} />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { fontSize: 18, fontWeight: 'bold', marginBottom: 10 },
  logs: { flex: 1, marginBottom: 10 },
  log: { fontFamily: 'monospace' },
  inputContainer: { flexDirection: 'row', alignItems: 'center' },
  input: { flex: 1, borderWidth: 1, borderColor: '#ccc', padding: 10, marginRight: 10 },
});
