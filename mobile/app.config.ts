import type { ExpoConfig } from 'expo/config';
const config: ExpoConfig = {
  name: 'QuotaCheck',
  extra: { nativeSmokeCheck: process.env.NATIVE_SMOKE_CHECK === '1' },
  slug: 'quota-check',
  version: '1.3.0',
  scheme: 'quota-check',
  orientation: 'default',
  userInterfaceStyle: 'automatic',
  icon: './assets/icon.png',
  ios: {
    supportsTablet: true,
    bundleIdentifier: process.env.IOS_BUNDLE_IDENTIFIER || 'com.fengluoxiao.quotacheck',
    buildNumber: process.env.IOS_BUILD_NUMBER || '13',
    infoPlist: {
      CFBundleDisplayName: '额度查询',
      ITSAppUsesNonExemptEncryption: true,
      NSLocalNetworkUsageDescription: '连接你自己部署的局域网额度服务。',
      NSAppTransportSecurity: { NSAllowsArbitraryLoads: true, NSAllowsLocalNetworking: true },
      CFBundleDocumentTypes: [
        {
          CFBundleTypeName: 'Quota Check Encrypted Connection',
          LSHandlerRank: 'Owner',
          LSItemContentTypes: ['com.fengluoxiao.quotacheck.connection'],
        },
      ],
      UTExportedTypeDeclarations: [
        {
          UTTypeIdentifier: 'com.fengluoxiao.quotacheck.connection',
          UTTypeDescription: 'Quota Check Encrypted Connection',
          UTTypeConformsTo: ['public.data'],
          UTTypeTagSpecification: {
            'public.filename-extension': ['sqv'],
            'public.mime-type': 'application/octet-stream',
          },
        },
      ],
    },
  },
  android: { package: 'com.fengluoxiao.quotacheck', versionCode: 13, permissions: ['INTERNET'] },
  plugins: [
    ['expo-secure-store', { configureAndroidBackup: true }],
    ['expo-file-system', { enableFileSharing: false, supportsOpeningDocumentsInPlace: false }],
    [
      'expo-build-properties',
      { ios: { deploymentTarget: '17.0' }, android: { usesCleartextTraffic: true } },
    ],
  ],
};
export default config;
