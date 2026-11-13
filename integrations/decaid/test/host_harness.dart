import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:reaprime/src/controllers/workflow_controller.dart';
import 'package:reaprime/src/models/device/grinder_device.dart';
import 'package:reaprime/src/plugins/plugin_ble_registry.dart';
import 'package:reaprime/src/plugins/plugin_manager.dart';
import 'package:reaprime/src/plugins/plugin_manifest.dart';

import '../helpers/plugin_ble_fixture.dart';
import 'plugin_test_helpers.dart';

const service = '5e5d6500-3f45-4b8c-9a65-28b4858d23d4';
const statusCharacteristic = '5e5d6502-3f45-4b8c-9a65-28b4858d23d4';

class AtomTransport extends PluginBleFixtureTransport {
  AtomTransport(super.physicalId) : super(services: const [service]);

  int dose = 180;
  int slot = 1;
  final commands = <Uint8List>[];

  Uint8List status({int sequence = 0, int result = 0}) {
    final bytes = [
      166,
      1,
      result,
      1,
      sequence & 255,
      sequence >> 8,
      dose & 255,
      dose >> 8,
      slot,
      0,
      50,
      0,
      16,
      39,
    ];
    return Uint8List.fromList([...bytes, bytes.fold(0, (a, b) => a ^ b)]);
  }

  @override
  Future<void> subscribe(
    String s,
    String c,
    void Function(Uint8List) callback,
  ) async {
    subscribers[c] = callback;
  }

  @override
  Future<Uint8List> read(String s, String c, {Duration? timeout}) async =>
      status();

  @override
  Future<void> write(
    String s,
    String c,
    Uint8List data, {
    bool withResponse = true,
    Duration? timeout,
  }) async {
    expect(s, service);
    expect(c, '5e5d6501-3f45-4b8c-9a65-28b4858d23d4');
    expect(withResponse, isTrue);
    expect(data.length, 8);
    expect(data.fold<int>(0, (a, b) => a ^ b), 0);
    commands.add(data);
    dose = data[5] | data[6] << 8;
    slot = 2;
    subscribers[statusCharacteristic]?.call(
      status(sequence: data[3] | data[4] << 8, result: 1),
    );
  }
}

void main() {
  test(
    'Atom65 package runs through real Decaid QuickJS, BLE Grinder, workflow events, HTTP, and KV',
    () async {
      final pluginDir = Platform.environment['ATOM65_PLUGIN_DIR']!;
      final manifest = PluginManifest.fromJson(
        jsonDecode(File('$pluginDir/manifest.json').readAsStringSync()),
      );
      expect(manifest.drivers.single.type, PluginDriverType.grinder);
      expect(manifest.drivers.single.grinderCapabilities, isEmpty);
      final manager = PluginManager(kvStore: FakeKeyValueStoreService());
      final workflow = WorkflowController();
      addTearDown(manager.dispose);
      addTearDown(workflow.dispose);
      manager.attachWorkflowController(workflow);
      await manager.loadPlugin(
        id: manifest.id,
        manifest: manifest,
        settings: {},
        jsCode: File('$pluginDir/plugin.js').readAsStringSync(),
      );
      await pumpEventQueue();
      final evidence = BleAdvertisementEvidence(serviceUuids: const [service]);
      final transports = <AtomTransport>[];
      Future<GrinderDevice> connect(String physicalId) async {
        final grinder =
            await manager.bleService.createCandidate(
                  driver: manager.bleService.registry
                      .decide(evidence)
                      .drivers
                      .single,
                  physicalId: physicalId,
                  evidence: evidence,
                  admit: () => true,
                  createTransport: () {
                    final t = AtomTransport(physicalId);
                    transports.add(t);
                    return t;
                  },
                )
                as GrinderDevice;
        await grinder.onConnect();
        return grinder;
      }

      final grinder = await connect('AA:BB');
      final other = await connect('CC:DD');
      await connect('EE:FF');
      await connect('11:22');
      await expectLater(connect('33:44'), throwsA(isA<Exception>()));

      var request = 0;
      Future<Map<String, dynamic>> api(
        String endpoint, {
        Map<String, dynamic>? body,
        String? deviceId,
      }) async {
        final requestId = 'atom-${request++}';
        final pending = manager.registerPendingHttp(manifest.id, requestId);
        manager.dispatchEvent(manifest.id, 'httpRequest', {
          'requestId': requestId,
          'method': body == null ? 'GET' : 'POST',
          'endpoint': endpoint,
          'query': {'deviceId': deviceId ?? grinder.deviceId},
          'body': body,
        });
        final response = await pending;
        expect(response['status'], inInclusiveRange(200, 299));
        return jsonDecode(response['body'] as String) as Map<String, dynamic>;
      }

      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(transports.every((t) => t.commands.isEmpty), isTrue);
      final initial = await api('status');
      expect(initial['loaded'], isTrue);
      expect(initial['rule'], {'mode': 'leave'});
      expect(initial['deviceId'], grinder.deviceId);
      // The skin can configure a library recipe without selecting it. Its
      // actual host serialization hashes to the same key on later selection.
      final libraryProfile = workflow.currentWorkflow.profile.copyWith(
        title: 'Library recipe',
      );
      final library = await api(
        'profile-settings',
        body: {'profile': libraryProfile.toJson()},
      );
      expect(library['rule'], {'mode': 'leave'});
      await api(
        'profile-settings',
        body: {
          'profile': libraryProfile.toJson(),
          'choice': {
            'profileKey': (library['profile'] as Map)['key'],
            'mode': 'fixed',
            'weight': 20.5,
          },
        },
      );
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(transports.every((t) => t.commands.isEmpty), isTrue);
      final originalProfile = workflow.currentWorkflow.profile;
      workflow.updateWorkflow(profile: libraryProfile);
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(transports.first.dose, 205);
      expect((await api('status'))['rule']['mode'], 'fixed');
      workflow.updateWorkflow(profile: originalProfile);
      transports.first.commands.clear();
      await api(
        'configure',
        body: {
          'profileKey': (initial['profile'] as Map)['key'],
          'mode': 'workflow',
          'enabled': true,
        },
      );
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(transports.first.commands.length, 1);
      expect(transports.first.dose, 180);
      expect(transports.last.commands, isEmpty);
      expect((await api('status'))['message'], contains('Synced'));
      workflow.updateWorkflow(
        context: workflow.currentWorkflow.context!.copyWith(
          targetDoseWeight: 19.2,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(transports.first.dose, 192);
      expect(transports.first.commands.length, 2);
      workflow.updateWorkflow(
        profile: workflow.currentWorkflow.profile.copyWith(
          title: 'Excluded profile',
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(transports.first.commands.length, 2);
      expect((await api('status'))['rule'], {'mode': 'leave'});
      expect((await api('status', deviceId: other.deviceId))['rules'], isEmpty);
      expect(manager.activePendingOpCount, 0);
      expect(grinder.capabilities, isEmpty);
    },
  );
}
