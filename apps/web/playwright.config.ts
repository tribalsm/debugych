import {defineConfig, devices} from '@playwright/test';
export default defineConfig({testDir:'../../tests/e2e',workers:1,timeout:60000,expect:{timeout:15000},use:{baseURL:process.env.PLAYWRIGHT_BASE_URL||'http://127.0.0.1:5173',trace:'retain-on-failure',screenshot:'only-on-failure'},reporter:[['list'],['html',{open:'never'}]],projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}]});
