import React from 'react';
import { View, FlatList, StyleSheet } from 'react-native';
import { Appbar, Card, Text, FAB, ActivityIndicator, useTheme, IconButton, Avatar } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';

const DeviceItem = ({ item, isConnected = false, onPress, onDisconnect }: { item: any, isConnected?: boolean, onPress: () => void, onDisconnect?: () => void }) => {
  const theme = useTheme();
  
  const LeftContent = (props: any) => isConnected ? (
    <Avatar.Icon {...props} icon="bluetooth-connect" size={40} style={{ backgroundColor: theme.colors.primaryContainer }} color={theme.colors.primary} />
  ) : (
    <View style={[styles.rssiBadge, { backgroundColor: theme.colors.secondaryContainer }]}>
       <Text style={[styles.rssiText, { color: theme.colors.onSecondaryContainer }]}>{item.rssi}</Text>
    </View>
  );

  const RightContent = (props: any) => isConnected ? (
    <IconButton {...props} icon="close-circle-outline" iconColor={theme.colors.error} onPress={onDisconnect} />
  ) : (
    <IconButton {...props} icon="chevron-right" iconColor={theme.colors.onSurfaceVariant} onPress={onPress} />
  );

  return (
    <Card 
      style={[
        styles.card, 
        isConnected && { borderColor: theme.colors.primary, borderWidth: 1, backgroundColor: theme.colors.surface }
      ]} 
      onPress={onPress} 
      mode={isConnected ? "outlined" : "elevated"}
    >
      <Card.Title
        title={item.name || 'Unnamed Device'}
        titleVariant="titleMedium"
        titleStyle={isConnected ? [styles.titleConnected, { color: theme.colors.primary }] : undefined}
        subtitle={isConnected ? 'Connected • Tap to open CLI' : `ID: ${item.id}`}
        subtitleStyle={isConnected ? { color: theme.colors.primary } : undefined}
        left={LeftContent}
        right={RightContent}
      />
    </Card>
  );
};

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

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Appbar.Header mode="center-aligned" elevated>
        <Appbar.Content title="Device Scanner" />
        {isScanning && <ActivityIndicator animating={true} color={theme.colors.primary} style={styles.activityIndicator} />}
      </Appbar.Header>
      
      <View style={styles.content}>
        {connectedDevice && (
            <View style={styles.connectedSection}>
                <Text variant="labelLarge" style={[styles.connectedLabel, { color: theme.colors.primary }]}>Connected Device</Text>
                <DeviceItem 
                  item={connectedDevice} 
                  isConnected={true} 
                  onPress={() => navigation.navigate('CLI' as never)}
                  onDisconnect={() => disconnect()}
                />
            </View>
        )}

        <FlatList
          data={availableDevices}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <DeviceItem 
              item={item} 
              isConnected={false} 
              onPress={() => handleConnect(item.id)}
            />
          )}
          ListHeaderComponent={
            availableDevices.length > 0 ? (
                <Text variant="labelLarge" style={[styles.listHeader, { color: theme.colors.onSurfaceVariant }]}>Available Devices</Text>
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
  },
  rssiText: {
    fontWeight: 'bold',
  },
  activityIndicator: {
    marginRight: 16,
  },
  connectedLabel: {
    marginLeft: 4,
    marginBottom: 8,
  },
  listHeader: {
    marginBottom: 8,
  },
  titleConnected: {
    fontWeight: '600',
  }
});
