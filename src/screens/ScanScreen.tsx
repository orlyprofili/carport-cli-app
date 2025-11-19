import React from 'react';
import { View, FlatList, StyleSheet } from 'react-native';
import { Appbar, Card, Text, FAB, ActivityIndicator, useTheme, IconButton, Avatar } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';

export const ScanScreen = () => {
  const { scan, stopScan, isScanning, devices, connect, connectedDevice, disconnect } = useBLE();
  const navigation = useNavigation();
  const theme = useTheme();

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

  const availableDevices = devices.filter(d => d.id !== connectedDevice?.id);

  const renderDeviceItem = ({ item, isConnected = false }: { item: any, isConnected?: boolean }) => (
    <Card 
      style={[
        styles.card, 
        isConnected && { borderColor: theme.colors.primary, borderWidth: 1, backgroundColor: theme.colors.surface }
      ]} 
      onPress={() => isConnected ? navigation.navigate('CLI' as never) : handleConnect(item.id)} 
      mode={isConnected ? "outlined" : "elevated"}
    >
      <Card.Title
        title={item.name || 'Unnamed Device'}
        titleVariant="titleMedium"
        titleStyle={isConnected ? { color: theme.colors.primary, fontWeight: '600' } : {}}
        subtitle={isConnected ? 'Connected • Tap to open CLI' : `ID: ${item.id}`}
        subtitleStyle={isConnected ? { color: theme.colors.primary } : {}}
        left={(props) => isConnected ? (
          <Avatar.Icon {...props} icon="bluetooth-connect" size={40} style={{ backgroundColor: theme.colors.primaryContainer }} color={theme.colors.primary} />
        ) : (
          <View style={[styles.rssiBadge, { backgroundColor: theme.colors.secondaryContainer }]}>
             <Text style={{ fontWeight: 'bold', color: theme.colors.onSecondaryContainer }}>{item.rssi}</Text>
          </View>
        )}
        right={(props) => isConnected ? (
          <IconButton {...props} icon="close-circle-outline" iconColor={theme.colors.error} onPress={() => disconnect()} />
        ) : (
          <IconButton {...props} icon="chevron-right" iconColor={theme.colors.onSurfaceVariant} onPress={() => handleConnect(item.id)} />
        )}
      />
    </Card>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Appbar.Header mode="center-aligned" elevated>
        <Appbar.Content title="Device Scanner" />
        {isScanning && <ActivityIndicator animating={true} color={theme.colors.primary} style={{ marginRight: 16 }} />}
      </Appbar.Header>
      
      <View style={styles.content}>
        {connectedDevice && (
            <View style={styles.connectedSection}>
                <Text variant="labelLarge" style={{ marginLeft: 4, marginBottom: 8, color: theme.colors.primary }}>Connected Device</Text>
                {renderDeviceItem({ item: connectedDevice, isConnected: true })}
            </View>
        )}

        <FlatList
          data={availableDevices}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => renderDeviceItem({ item, isConnected: false })}
          ListHeaderComponent={
            availableDevices.length > 0 ? (
                <Text variant="labelLarge" style={{ marginBottom: 8, color: theme.colors.onSurfaceVariant }}>Available Devices</Text>
            ) : null
          }
          ListEmptyComponent={
            !connectedDevice ? (
                <View style={styles.emptyState}>
                <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant }}>
                    {isScanning ? 'Searching for devices...' : 'Press Scan to start'}
                </Text>
                </View>
            ) : null
          }
        />
      </View>

      <FAB
        icon={isScanning ? 'stop' : 'magnify'}
        style={[styles.fab, { backgroundColor: theme.colors.primaryContainer }]}
        onPress={toggleScan}
        label={isScanning ? 'Stop' : 'Scan'}
        color={theme.colors.onPrimaryContainer}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  content: { flex: 1 },
  listContent: { padding: 16, paddingBottom: 80 },
  connectedSection: { padding: 16, paddingBottom: 0 },
  card: { marginBottom: 12 },
  fab: {
    position: 'absolute',
    margin: 16,
    right: 0,
    bottom: 0,
  },
  emptyState: {
    padding: 20,
    alignItems: 'center',
    marginTop: 50,
  },
  rssiBadge: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  }
});
