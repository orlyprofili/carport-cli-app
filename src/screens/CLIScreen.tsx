import React, { useState, useRef } from 'react';
import { View, FlatList, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { Appbar, TextInput, Text, Surface, useTheme } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { SafeAreaView } from 'react-native-safe-area-context';

export const CLIScreen = () => {
  const { connectedDevice, sendMessage, logs, disconnect } = useBLE();
  const [input, setInput] = useState('');
  const flatListRef = useRef<FlatList>(null);
  const theme = useTheme();

  if (!connectedDevice) {
    return (
      <View style={styles.center}>
        <Text variant="headlineMedium" style={{ color: theme.colors.secondary, marginBottom: 8 }}>No device connected</Text>
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant }}>Please connect to a device from the Scan tab.</Text>
      </View>
    );
  }

  const handleSend = () => {
    if (input.trim()) {
      sendMessage(input);
      setInput('');
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Appbar.Header elevated>
        <Appbar.Content title={connectedDevice.name || 'Unknown Device'} subtitle="Connected" />
        <Appbar.Action icon="lan-disconnect" onPress={disconnect} color={theme.colors.error} />
      </Appbar.Header>

      <Surface style={styles.terminal} elevation={2}>
        <FlatList
          ref={flatListRef}
          data={logs}
          keyExtractor={(_, i) => i.toString()}
          renderItem={({ item }) => (
            <Text style={styles.log}>{item}</Text>
          )}
          contentContainerStyle={styles.logsContent}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
        />
      </Surface>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
      >
        <View style={[styles.inputContainer, { backgroundColor: theme.colors.surface }]}>
          <TextInput
            mode="outlined"
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Enter command..."
            right={<TextInput.Icon icon="send" onPress={handleSend} disabled={!input.trim()} />}
            onSubmitEditing={handleSend}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  terminal: {
    flex: 1,
    margin: 16,
    borderRadius: 12,
    backgroundColor: '#1E1E1E', // VS Code dark theme background-ish
    overflow: 'hidden',
  },
  logsContent: { padding: 16 },
  log: { 
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', 
    fontSize: 13, 
    marginBottom: 4, 
    color: '#4CAF50' // Terminal green
  },
  inputContainer: {
    padding: 16,
    paddingBottom: Platform.OS === 'ios' ? 16 : 16,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.05)',
  },
  input: { backgroundColor: 'white' },
});
