import React from 'react';
import { View, FlatList, StyleSheet } from 'react-native';
import { Appbar, Card, Text, FAB, ActivityIndicator, useTheme } from 'react-native-paper';
import { useBLE } from '../context/BLEContext';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';

export const ScanScreen = () => {
  const { scan, stopScan, isScanning, devices, connect } = useBLE();
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

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Appbar.Header mode="center-aligned" elevated>
        <Appbar.Content title="Device Scanner" />
        {isScanning && <ActivityIndicator animating={true} color={theme.colors.primary} style={{ marginRight: 16 }} />}
      </Appbar.Header>
      
      <View style={styles.content}>
        <FlatList
          data={devices}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <Card style={styles.card} onPress={() => handleConnect(item.id)} mode="elevated">
              <Card.Title
                title={item.name || 'Unnamed Device'}
                titleVariant="titleMedium"
                subtitle={`ID: ${item.id}`}
                subtitleVariant="bodySmall"
                left={(props) => (
                  <View style={[styles.rssiBadge, { backgroundColor: theme.colors.secondaryContainer }]}>
                     <Text style={{ fontWeight: 'bold', color: theme.colors.onSecondaryContainer }}>{item.rssi}</Text>
                  </View>
                )}
              />
            </Card>
          )}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant }}>
                {isScanning ? 'Searching for devices...' : 'Press Scan to start'}
              </Text>
            </View>
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
