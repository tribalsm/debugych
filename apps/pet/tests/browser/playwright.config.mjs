import{defineConfig}from'@playwright/test';
export default defineConfig({testDir:'.',testMatch:'*.spec.mjs',workers:1,timeout:30000,use:{baseURL:'http://127.0.0.1:8794',viewport:{width:1000,height:1000},screenshot:'only-on-failure',trace:'retain-on-failure'},outputDir:'../../evidence/v321/browser-results',reporter:[['list']]});
