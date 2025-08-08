import { type RequestHandler } from '@sveltejs/kit';
import { db } from '$lib/db/client';
import { signalConfigs, sourceConfigs, sources } from '$lib/db/schema';
import { eq, and } from 'drizzle-orm';
import { loadSignalConfigs } from '$lib/utils/config-loader';
import { deriveSignalType } from '$lib/utils/signals';

interface DeviceActivateRequest {
	device_id: string;
	pairing_code: string; // Changed from device_token
	device_name: string;
	device_type: string;
	user_id: string;
	source_names?: string[]; // Optional: specific sources to connect
}

export const POST: RequestHandler = async ({ request }) => {
	try {
		const body: DeviceActivateRequest = await request.json();
		console.log('Device activation request:', body);

		// Validate required fields
		if (!body.device_id || !body.pairing_code || !body.device_name || !body.device_type) {
			return new Response(JSON.stringify({
				error: 'Missing required fields: device_id, pairing_code, device_name, device_type'
			}), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Use the device type as the source name (ios, mac, etc.)
		const sourceName = body.device_type;

		// First, check if the source configuration exists
		const [sourceConfig] = await db
			.select()
			.from(sourceConfigs)
			.where(eq(sourceConfigs.name, sourceName))
			.limit(1);

		if (!sourceConfig) {
			console.error(`Source type '${sourceName}' not found. Available sources should include: ios, mac, android`);
			return new Response(JSON.stringify({
				error: `Source type '${sourceName}' not found`,
				details: `The source type '${sourceName}' does not exist. Make sure you're using a valid device type like 'ios', 'mac', or 'android'.`,
				availableTypes: ['ios', 'mac', 'android']
			}), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Check if pairing window is active and code matches
		const now = new Date();
		const isPairingActive = sourceConfig.pairingExpiresAt && sourceConfig.pairingExpiresAt > now;

		if (!isPairingActive) {
			console.log(`Pairing attempt for ${sourceName} failed: no active pairing window. Pairing expires at: ${sourceConfig.pairingExpiresAt?.toISOString() || 'null'}, current time: ${now.toISOString()}`);
			return new Response(JSON.stringify({
				error: 'No active pairing window',
				details: 'Start pairing mode on the web app first, then try connecting your device within 60 seconds.',
				pairing_expires_at: sourceConfig.pairingExpiresAt?.toISOString() || null,
				current_time: now.toISOString()
			}), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Validate pairing code
		if (sourceConfig.pairingCode !== body.pairing_code) {
			console.log(`Pairing attempt failed: invalid code. Expected: ${sourceConfig.pairingCode}, got: ${body.pairing_code}`);
			return new Response(JSON.stringify({
				error: 'Invalid pairing code',
				details: 'The pairing code is incorrect. Please check the 6-digit code shown on the web app.'
			}), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		console.log(`Pairing window is active for ${sourceName}, proceeding with device activation`);

		// Check if this device is already registered
		const existingDevice = await db
			.select()
			.from(sources)
			.where(
				and(
					eq(sources.deviceId, body.device_id),
					eq(sources.sourceName, sourceName)
				)
			)
			.limit(1);

		if (existingDevice.length > 0) {
			console.log(`Device ${body.device_id} is already registered`);
			return new Response(JSON.stringify({
				error: 'Device already registered',
				details: 'This device is already registered. Please use the existing device token.'
			}), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Generate a permanent device token
		const deviceToken = `dev_tk_${crypto.randomUUID()}`;

		// Create a new source instance for this device
		const [deviceSource] = await db
			.insert(sources)
			.values({
				sourceName: sourceName,
				instanceName: body.device_name,
				isActive: true,
				deviceId: body.device_id,
				deviceToken: deviceToken,
				deviceType: body.device_type,
				metadata: {
					pairedAt: new Date().toISOString(),
					deviceInfo: {
						name: body.device_name,
						type: body.device_type
					}
				},
				lastSyncAt: new Date(),
				createdAt: new Date(),
				updatedAt: new Date()
			})
			.returning();

		if (!deviceSource) {
			console.error(`Failed to create source instance for '${sourceName}' - this should not happen`);
			return new Response(JSON.stringify({
				error: `Failed to create source instance for '${sourceName}'`,
				details: `The source creation operation failed unexpectedly.`
			}), {
				status: 500,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Clear the pairing window from source_configs
		await db
			.update(sourceConfigs)
			.set({
				pairingCode: null,
				pairingExpiresAt: null,
				updatedAt: new Date()
			})
			.where(eq(sourceConfigs.name, sourceName));

		// Load signal configurations from file
		let signalConfigsFromFile: Record<string, Array<any>> = {};

		try {
			const signalsConfig = loadSignalConfigs();
			// Group signals by source_name
			for (const signal of signalsConfig.signals) {
				if (!signalConfigsFromFile[signal.source_name]) {
					signalConfigsFromFile[signal.source_name] = [];
				}
				signalConfigsFromFile[signal.source_name].push({
					signalId: signal.signal_name,
					signalType: deriveSignalType(signal.signal_name),
					unit: signal.unit_ucum,
					computation: signal.computation,
					description: signal.description,
					syncSchedule: signal.cron_schedule
				});
			}
		} catch (error) {
			console.error('Failed to load signals config:', error);
			// Fall back to minimal config for iOS devices
			signalConfigsFromFile = {
				[body.device_type]: [
					{
						signalId: `${body.device_type}_speed`,
						signalType: deriveSignalType(`${body.device_type}_speed`),
						unit: 'm/s',
						computation: { algorithm: 'pelt', value_type: 'continuous', cost_function: 'l1' }
					},
					{
						signalId: `${body.device_type}_sound_classification`,
						signalType: deriveSignalType(`${body.device_type}_sound_classification`),
						unit: 'classification',
						computation: { algorithm: 'basic', value_type: 'categorical' }
					}
				]
			};
		}

		// Activate existing signals for this device source
		const signalIds: string[] = [];
		const activatedSignals: string[] = [];

		// Get all signals for this source from database
		const sourceSignals = await db
			.select()
			.from(signalConfigs)
			.where(eq(signalConfigs.sourceName, sourceName));

		if (sourceSignals.length === 0) {
			console.error(`No signals found for source '${sourceName}'. Please run database seeding.`);
			return new Response(JSON.stringify({
				error: `No signals configured for source '${sourceName}'`,
				details: `Please ensure database is properly seeded with signals from signalConfigs.json`
			}), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Update each signal to active status and add device metadata
		for (const signal of sourceSignals) {
			const deviceMetadata = {
				device_id: body.device_id,
				device_name: body.device_name,
				device_type: body.device_type,
				activated_at: new Date().toISOString()
			};

			// Merge with existing settings
			const updatedSettings = {
				...(signal.settings || {}),
				device: deviceMetadata,
				sourceInstanceId: deviceSource.id
			};

			const [updatedSignal] = await db
				.update(signalConfigs)
				.set({
					status: 'active',
					settings: updatedSettings,
					sourceId: deviceSource.id,
					updatedAt: new Date()
				})
				.where(eq(signalConfigs.id, signal.id))
				.returning();

			signalIds.push(updatedSignal.id);
			activatedSignals.push(signal.signalName);
		}

		const response = {
			status: 'success',
			device_id: body.device_id,
			device_token: deviceToken, // Return the permanent token
			source_name: sourceName,
			signal_ids: { [sourceName]: signalIds },
			connection_ids: { [sourceName]: signalIds }, // iOS app expects this key for backward compatibility
			message: `Device activated with ${signalIds.length} signals`,
			activated_signals: activatedSignals
		};

		console.log(`✅ Device activation successful: ${body.device_name} (${body.device_type}) activated ${signalIds.length} signals for ${sourceName}`);
		console.log('Full response:', response);

		return new Response(JSON.stringify(response), {
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Device activation error:', error);

		// Return more specific error information
		let errorMessage = 'Failed to activate device';
		let statusCode = 500;
		
		if (error instanceof Error) {
			// Check for foreign key constraint error
			errorMessage = `Device activation failed: ${error.message}`;
		}

		return new Response(JSON.stringify({
			error: errorMessage,
			details: error instanceof Error ? error.message : 'Unknown error',
			timestamp: new Date().toISOString()
		}), {
			status: statusCode,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};