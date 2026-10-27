const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({testDir:'.',testMatch:'shell.spec.cjs',workers:1,timeout:15000,use:{headless:true,viewport:{width:1360,height:900}},reporter:'list'});
