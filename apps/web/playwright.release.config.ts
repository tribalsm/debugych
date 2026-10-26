import {defineConfig} from '@playwright/test';
import base from './playwright.config';
// Explicit free-only allowlist. Never sweep live-provider E2E into a release check.
export default defineConfig({...base,testMatch:['**/web-release.spec.ts','**/desktop-result-links.spec.ts','**/validation-binding.spec.ts','**/workflow.spec.ts','**/redesign.spec.ts'],outputDir:'../../outputs/web-integration/browser-results',reporter:[['list']]});
