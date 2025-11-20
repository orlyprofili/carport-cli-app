import React, { useCallback } from 'react';
import { View, FlatList, StyleSheet, RefreshControl } from 'react-native';
import { Card, Text, useTheme, IconButton, Avatar, Surface } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';

const DeviceLeft = ({ isConnected, item, theme, ...props }: any) => {
  if (isConnected) {
    return <Avatar.Icon {...props} icon="bluetooth-connect" size={40} style={{ backgroundColor: theme.colors.primaryContainer }} color={theme.colors.primary} />;
  }
  return (
    <View style={[styles.rssiBadge, { backgroundColor: theme.colors.secondaryContainer }]}>
       <Text style={[styles.rssiText, { color: theme.colors.onSecondaryContainer }]}>{item.rssi}</Text>
    </View>
  );
};

const DeviceRight = ({ isConnected, onDisconnect, onPress, theme, ...props }: any) => {
  if (isConnected) {
    return <IconButton {...props} icon="link-variant-off" iconColor={theme.colors.error} onPress={onDisconnect} />;
  }
  return <IconButton {...props} icon="chevron-right" iconColor={theme.colors.onSurfaceVariant} onPress={onPress} />;
};

const DeviceItem = ({ item, isConnected = false, onPress, onDisconnect }: { item: any, isConnected?: boolean, onPress: () => void, onDisconnect?: () => void }) => {
  const theme = useTheme();

  const renderLeft = useCallback((props: any) => (
    <DeviceLeft {...props} isConnected={isConnected} item={item} theme={theme} />
  ), [isConnected, item, theme]);

  const renderRight = useCallback((props: any) => (
    <DeviceRight {...props} isConnected={isConnected} onDisconnect={onDisconnect} onPress={onPress} theme={theme} />
  ), [isConnected, onDisconnect, onPress, theme]);
  
  return (
    <Card 
      style={[
        styles.card, 
        isConnected && styles.cardConnected
      ]} 
      onPress={onPress} 
      mode={isConnected ? "outlined" : "elevated"}
    >
      <Card.Title
        title={item.name || 'Unnamed Device'}
        titleVariant="titleMedium"
        titleStyle={[
          styles.monotonFont,
          isConnected && styles.titleConnected,
          isConnected && { color: theme.colors.primary }
        ]}
        subtitle={isConnected ? 'Connected • Tap to open CLI' : `ID: ${item.id}`}
        subtitleStyle={isConnected ? { color: theme.colors.primary } : undefined}
        left={renderLeft}
        right={renderRight}
      />
    </Card>
  );
};

export const ScanScreen = () => {
  const { scan, isScanning, devices, connect, connectedDevice, disconnect } = useBLE();
  const navigation = useNavigation();
  const theme = useTheme();

  const handleConnect = async (id: string) => {
    await connect(id);
    navigation.navigate('CLI' as never);
  };

  const availableDevices = devices.filter(d => d.id !== connectedDevice?.id);

  const renderHeader = () => (
    <View>
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
      {availableDevices.length > 0 && (
        <Text variant="labelLarge" style={[styles.listHeader, { color: theme.colors.onSurfaceVariant }, connectedDevice && styles.listHeaderWithConnection]}>Available Devices</Text>
      )}
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Surface elevation={2} style={[styles.headerSurface, { backgroundColor: theme.colors.surface }]}>
        <View>
          <Text variant="displaySmall" style={[styles.headerText, { color: theme.colors.onSurface }]}>Device</Text>
          <Text variant="displaySmall" style={[styles.headerText, { color: theme.colors.onSurface }]}>Scanner</Text>
        </View>
      </Surface>
      
      <View style={styles.content}>
        <FlatList
          data={availableDevices}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={isScanning}
              onRefresh={scan}
              colors={[theme.colors.primary]}
              tintColor={theme.colors.primary}
            />
          }
          renderItem={({ item }) => (
            <DeviceItem 
              item={item} 
              isConnected={false} 
              onPress={() => handleConnect(item.id)}
            />
          )}
          ListHeaderComponent={renderHeader}
          ListEmptyComponent={
            !connectedDevice ? (
                <View style={styles.emptyState}>
                <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant }}>
                    {isScanning ? 'Searching for devices...' : 'Pull down to scan'}
                </Text>
                </View>
            ) : null
          }
        />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  content: { flex: 1 },
  listContent: { padding: 16, paddingBottom: 80, flexGrow: 1 },
  connectedSection: { padding: 16, paddingBottom: 0 },
  card: { marginBottom: 12 },
  listHeaderWithConnection: {
    marginTop: 16,
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
  },
  cardConnected: {
    borderWidth: 1,
  },
  monotonFont: {
    fontFamily: 'Monoton-Regular',
  },
  headerSurface: {
    paddingHorizontal: 16,
    paddingVertical: 24,
  },
  headerText: {
    fontFamily: 'Monoton-Regular',
    lineHeight: 50,
    paddingVertical: 4,
  },
});
