import React, { useState, useRef } from 'react';
import { View, FlatList, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { Appbar, TextInput, Text, Surface, useTheme, Button } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { SafeAreaView } from 'react-native-safe-area-context';

export const CLIScreen = () => {
  const { connectedDevice, sendMessage, disconnect, cliOutput, monitorOutput, clearCliOutput, clearMonitorOutput } = useBLE();
  const [input, setInput] = useState('');
  const cliListRef = useRef<FlatList>(null);
  const monitorListRef = useRef<FlatList>(null);
  const theme = useTheme();

  if (!connectedDevice) {
    return (
      <View style={styles.center}>
        <Text variant="headlineMedium" style={[styles.noDeviceText, { color: theme.colors.secondary }]}>No device connected</Text>
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
      <Appbar.Header mode="small" elevated style={{ backgroundColor: theme.colors.surface }}>
        <Appbar.Content title={connectedDevice.name || 'Unknown Device'} subtitle="Connected" />
        <Appbar.Action icon="link-variant-off" onPress={disconnect} color={theme.colors.error} />
      </Appbar.Header>

      <View style={styles.splitPane}>
        {/* CLI Console */}
        <Surface style={styles.pane} elevation={1}>
          <View style={styles.paneHeader}>
            <Text variant="titleSmall" style={styles.paneTitle}>CLI Console</Text>
            <Button compact onPress={clearCliOutput} textColor={theme.colors.primary}>Clear</Button>
          </View>
          <FlatList
            ref={cliListRef}
            data={cliOutput}
            keyExtractor={(_, i) => i.toString()}
            renderItem={({ item }) => <Text style={styles.logText}>{item}</Text>}
            contentContainerStyle={styles.listContent}
            onContentSizeChange={() => cliListRef.current?.scrollToEnd({ animated: true })}
          />
        </Surface>

        {/* Monitor Logs */}
        <Surface style={styles.pane} elevation={1}>
          <View style={styles.paneHeader}>
            <Text variant="titleSmall" style={styles.paneTitle}>Monitor Logs</Text>
            <Button compact onPress={clearMonitorOutput} textColor={theme.colors.primary}>Clear</Button>
          </View>
          <FlatList
            ref={monitorListRef}
            data={monitorOutput}
            keyExtractor={(_, i) => i.toString()}
            renderItem={({ item }) => <Text style={styles.logText}>{item}</Text>}
            contentContainerStyle={styles.listContent}
            onContentSizeChange={() => monitorListRef.current?.scrollToEnd({ animated: true })}
          />
        </Surface>
      </View>

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
  splitPane: { flex: 1, padding: 8, gap: 8 },
  pane: { flex: 1, borderRadius: 8, backgroundColor: '#1E1E1E', overflow: 'hidden' },
  paneHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 4, backgroundColor: '#2D2D2D' },
  paneTitle: { color: '#ccc', fontWeight: 'bold' },
  listContent: { padding: 8 },
  logText: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 12, color: '#eee' },
  inputContainer: {
    padding: 16,
    paddingBottom: Platform.OS === 'ios' ? 16 : 16,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.05)',
  },
  input: { backgroundColor: 'white' },
  noDeviceText: { marginBottom: 8 },
});
